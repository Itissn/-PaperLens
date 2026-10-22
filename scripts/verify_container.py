"""Opt-in isolated Docker integration verification; never installs a container runtime."""
import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import time
import uuid
from pathlib import Path
from scripts.container_preflight import ROOT, validate_assets

class VerificationFailure(RuntimeError):
    pass

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]

def read_events(lines):
    """Bound SSE consumption and reject transport/application errors before a result."""
    events = []
    current = None
    size = 0
    for line in lines:
        size += len(line)
        if size > 2_000_000:
            raise VerificationFailure("Agent event limit exceeded.")
        if line.startswith("event:"):
            current = line[6:].strip()
        elif line.startswith("data:"):
            data = json.loads(line[5:].strip())
            events.append(current)
            if current == "error":
                raise VerificationFailure("Agent reported an application error.")
            if current == "result":
                return events,data
    raise VerificationFailure("Agent stream ended without a result.")

def assert_agent_result(events, result):
    agent = result.get("agent",{})
    tools = {t["tool"] for t in agent.get("trace",[]) if t["outcome"] == "ok"}
    text = " ".join(p["text"] for p in result.get("paragraphs",[]))
    if not (result.get("status") == "generated" and re.search(r"\b30\b",text)
            and result.get("semantic_check",{}).get("passed")
            and result.get("validation",{}).get("passed")
            and agent.get("all_cited_pages_read")
            and {"search_papers","read_page"}.issubset(tools)
            and 0 < agent.get("tool_calls",0) <= 6
            and "draft" in events
            and any(c["page"] == 8 for c in result.get("citations",[]))):
        raise VerificationFailure("Real Agent inference did not meet the source-backed smoke criteria.")

class ContainerVerifier:
    def __init__(self,root=ROOT,runner=subprocess.run,asset_check=validate_assets,timeout=1800,keep_image=False):
        self.root = Path(root).resolve()
        self.runner = runner
        self.asset_check = asset_check
        self.timeout = timeout
        self.keep_image = keep_image
        self.private_values = []
        self.project = "paperlens-verify-"+uuid.uuid4().hex[:12]
        self.image = self.project+":test"
        self.env = dict(os.environ)
        for name in ("COMPOSE_FILE","COMPOSE_PROFILES","COMPOSE_PROJECT_NAME"):
            self.env.pop(name,None)
        self.env.update(PAPERLENS_PORT=str(free_port()),PAPERLENS_APP_IMAGE=self.image)
        self.base = ["docker","compose","--project-directory",str(self.root),
                     "--file",str(self.root/"compose.yaml"),"--project-name",self.project]
        self.report = {"runtime_tested":False,"passed":False,"project":self.project,
                       "checks":[],"cleanup_passed":False,"image":self.image,"image_retained":False}
        self.phase = "preflight"

    def command(self,*args,compose=True,password=None,timeout=None):
        command = (self.base if compose else ["docker"])+list(args)
        if password is not None:self.private_values.append(password)
        try:
            result = self.runner(command,cwd=self.root,env=self.env,check=True,
                                 input=(password+"\n") if password is not None else None,
                                 capture_output=True,text=True,encoding="utf-8",
                                 timeout=timeout or self.timeout)
        except subprocess.CalledProcessError as exc:
            self.report["command_error"] = {"exit_code":exc.returncode,
                "output_tail":self.safe_diagnostic(exc.stdout,exc.stderr)}
            raise
        return result.stdout.strip()

    def safe_diagnostic(self,*parts):
        values = list(self.private_values)
        key_path = Path(self.env.get("PAPERLENS_LLM_KEY_FILE_HOST") or ".cache/local-llm/api-key.txt")
        if not key_path.is_absolute():key_path = self.root/key_path
        try:values.append(key_path.read_text(encoding="ascii").strip())
        except (OSError,UnicodeError):pass
        values += [v for k,v in self.env.items() if re.search("TOKEN|PASSWORD|SECRET",k,re.I)]
        def decoded(value):return value.decode("utf-8",errors="replace") if isinstance(value,bytes) else (value or "")
        output = "\n".join(decoded(v) for v in parts)
        for value in values:
            if len(value) >= 8:output = output.replace(value,"[REDACTED]")
        output = re.sub(r"(?i)Bearer\s+[A-Za-z0-9_.~+/-]+=*","Bearer [REDACTED]",output)
        return output[-6000:]

    def step(self,name):
        self.phase = name
        print("Container check: "+name,flush=True)

    def passed(self):
        self.report["checks"].append({"name":self.phase,"passed":True})

    def wait_ready(self,client):
        end = time.monotonic()+self.timeout
        next_state_check = 0
        restarting = {}
        while time.monotonic() < end:
            try:
                response = client.get("/api/readiness",timeout=8)
                body = response.json()
                if response.status_code == 200 and body.get("ready"):
                    return
                checks = body.get("checks",{}) if isinstance(body,dict) else {}
                self.report["last_readiness"] = {"status_code":response.status_code,
                    "checks":{k:v for k,v in checks.items() if isinstance(v,bool)}}
            except Exception:
                pass
            if time.monotonic() >= next_state_check:
                raw = self.command("ps","--all","--format","json",timeout=20)
                if raw:
                    try:
                        states = json.loads(raw)
                        if isinstance(states,dict):states = [states]
                    except json.JSONDecodeError:
                        states = [json.loads(line) for line in raw.splitlines() if line.strip()]
                    for state in states:
                        service = state.get("Service")
                        if service not in ("paperlens","llm"):continue
                        health = state.get("Health","")
                        status = state.get("State","")
                        restarting[service] = restarting.get(service,0)+1 if status == "restarting" else 0
                        if health == "unhealthy" or status in ("exited","dead","removing") or restarting[service] >= 3:
                            self.report["failed_container"] = {"service":service,"state":status,"health":health}
                            raise VerificationFailure("Required container is unhealthy, stopped or repeatedly restarting.")
                next_state_check = time.monotonic()+15
            time.sleep(2)
        raise VerificationFailure("Container readiness timed out.")

    def check_api(self,password):
        import httpx
        base = "http://127.0.0.1:"+self.env["PAPERLENS_PORT"]
        # Ignore proxy environment settings for private localhost application tests.
        with httpx.Client(base_url=base,timeout=180,trust_env=False) as admin, \
             httpx.Client(base_url=base,timeout=180,trust_env=False) as viewer, \
             httpx.Client(base_url=base,timeout=8,trust_env=False) as anonymous:
            self.step("protected readiness")
            self.wait_ready(anonymous)
            assert anonymous.get("/api/documents").status_code == 401
            response = admin.post("/api/auth/login",json={"username":"verifier_admin","password":password})
            response.raise_for_status()
            assert response.json()["role"] == "admin"
            cookie = response.headers["set-cookie"].lower()
            assert "httponly" in cookie and "samesite=strict" in cookie
            assert admin.get("/api/auth/me").json()["authentication_required"]
            self.passed()

            self.step("public corpus and hybrid retrieval")
            status = admin.get("/api/status").json()
            assert status["documents"] == 3 and status["chunks"] == status["embedded_chunks"] == 146
            response = admin.post("/api/ask",json={"question":"How many random seeds were used in the BN-GPGLS experiments?","mode":"hybrid","rerank":True})
            response.raise_for_status()
            evidence = response.json()
            assert evidence["status"] == "evidence" and evidence["citations"]
            cid = evidence["conversation_id"]
            self.passed()

            self.step("real local model Agent SSE and source checks")
            with admin.stream("POST","/api/agent/stream",json={
                "question":"How many random seeds were used in the BN-GPGLS experiments? Search the papers and inspect the relevant page.",
                "generator":"local_llm","mode":"hybrid"},timeout=httpx.Timeout(900,connect=10)) as response:
                response.raise_for_status()
                events,result = read_events(response.iter_lines())
            self.report["agent"] = {"status":result.get("status"),
                "tool_calls":result.get("agent",{}).get("tool_calls"),
                "source_validation":bool(result.get("validation",{}).get("passed")),
                "semantic_check":bool(result.get("semantic_check",{}).get("passed")),
                "all_cited_pages_read":bool(result.get("agent",{}).get("all_cited_pages_read")),
                "sse_drafts":"draft" in events}
            assert_agent_result(events,result)
            self.report["agent"] = {"status":result["status"],"tool_calls":result["agent"]["tool_calls"],
                                    "source_checks_passed":True,"sse_drafts":True}
            self.passed()

            self.step("roles and owner isolation")
            viewer_password = secrets.token_urlsafe(24)
            response = admin.post("/api/admin/users",json={"username":"verifier_viewer","password":viewer_password,"role":"viewer"})
            response.raise_for_status()
            viewer.post("/api/auth/login",json={"username":"verifier_viewer","password":viewer_password}).raise_for_status()
            assert viewer.post("/api/index").status_code == 403
            assert viewer.get("/api/metrics").status_code == 403
            assert viewer.get("/api/conversations/"+cid).status_code == 404
            assert viewer.post("/api/documents",files={"file":("denied.pdf",b"%PDF","application/pdf")}).status_code == 403
            self.passed()

            self.step("Linux OCR table and formula extraction")
            from scripts.sample_pdf import scanned_pdf,structured_pdf
            scan = admin.post("/api/documents",files={"file":("container-ocr-fixture.pdf",scanned_pdf(),"application/pdf")},data={"ocr":"true"})
            scan.raise_for_status()
            scan_id = scan.json()["document"]["id"]
            page = admin.get("/api/documents/"+scan_id+"/pages/1/structure?ocr=true")
            page.raise_for_status()
            ocr_text = " ".join(line["text"] for line in page.json()["ocr_lines"]).lower()
            assert "30" in ocr_text and "random seeds" in ocr_text
            table = admin.post("/api/documents",files={"file":("container-structure-fixture.pdf",structured_pdf(),"application/pdf")})
            table.raise_for_status()
            table_id = table.json()["document"]["id"]
            structure = admin.get("/api/documents/"+table_id+"/pages/1/structure").json()
            assert structure["tables"][0]["rows"] == [["Method","Seeds"],["Baseline","30"]]
            formula = structure["formulas"][0]
            assert formula["symbolic"]["parsed"]
            crop = admin.get("/api/documents/"+table_id+"/pages/1/image",params={"bbox":",".join(map(str,formula["bbox"]))})
            assert crop.status_code == 200 and crop.content.startswith(b"\x89PNG")
            self.passed()

            self.step("volume persistence after container recreation")
            before = admin.get("/api/status").json()
            docs_before = admin.get("/api/documents").json()
            history_before = admin.get("/api/conversations/"+cid).json()
            # Recreation, not only process restart, establishes that data is in volumes.
            self.command("up","-d","--no-deps","--force-recreate","paperlens")
            self.wait_ready(anonymous)
            after = admin.get("/api/status").json()
            for field in ("documents","chunks","embedded_chunks"):
                assert before[field] == after[field]
            assert admin.get("/api/documents").json() == docs_before
            assert admin.get("/api/conversations/"+cid).json() == history_before
            assert admin.get("/api/auth/me").json()["role"] == "admin"
            assert admin.post("/api/index").status_code == 200
            self.passed()

            self.step("logout revocation")
            admin.post("/api/auth/logout").raise_for_status()
            assert admin.get("/api/conversations").status_code == 401
            self.passed()

    def run(self):
        cleanup_needed = False
        built = False
        success = False
        try:
            self.asset_check(self.root,self.env)
            self.passed()
            self.step("local Linux daemon")
            # Refuse accidental external deployment via a remote Docker context.
            endpoint = self.env.get("DOCKER_HOST") or self.command("context","inspect","--format","{{.Endpoints.docker.Host}}",compose=False)
            if not endpoint.startswith(("unix://","npipe://")):
                raise VerificationFailure("Use a local Docker daemon, not a remote context.")
            server_os = self.command("version","--format","{{.Server.Os}}",compose=False)
            if server_os != "linux":
                raise VerificationFailure("A Linux container daemon is required.")
            self.report["daemon_checked"] = True
            self.passed()
            self.step("Compose contract")
            self.command("config","--quiet")
            if self.command("ps","--all","--quiet"):
                raise VerificationFailure("The generated verification project already exists.")
            self.passed()
            self.step("image build")
            self.command("build","paperlens")
            built = True
            self.passed()
            cleanup_needed = True
            self.report["runtime_tested"] = True
            self.step("private administrator bootstrap")
            password = secrets.token_urlsafe(24)
            self.command("run","--rm","--no-deps","-T","paperlens","python","manage.py",
                         "user-add","--username","verifier_admin","--role","admin","--password-stdin",password=password)
            self.passed()
            self.step("non-root mounted model key access")
            self.command("run","--rm","--no-deps","-T","paperlens","python","-c",
                         "import os; from pathlib import Path; assert os.geteuid()==10001; assert len(Path('/run/secrets/llm_key').read_text().strip())>=32")
            self.passed()
            self.step("corpus model and index bootstrap")
            self.command("run","--rm","--no-deps","bootstrap")
            self.passed()
            self.step("application and model startup")
            self.command("up","-d","paperlens")
            self.passed()
            self.check_api(password)
            success = True
        except (Exception,KeyboardInterrupt) as exc:
            self.report["failure"] = {"phase":self.phase,"type":type(exc).__name__,
                                      "message":"Verification did not complete. No credentials or response bodies are recorded."}
            if cleanup_needed:
                if self.report.get("last_readiness",{}).get("checks",{}).get("bootstrap") is False:
                    try:
                        self.command("exec","-T","paperlens","python","-c",
                            "from pathlib import Path; from paperlens.deployment import _marker_assets; _marker_assets(Path('/app'))",timeout=20)
                    except Exception:pass
                try:
                    self.report["container_logs_tail"] = self.safe_diagnostic(
                        self.command("logs","--no-color","--tail","50","llm","paperlens",timeout=20))
                except Exception:
                    self.report["diagnostics_available"] = False
        finally:
            cleanup_ok = True
            if cleanup_needed:
                try:self.command("down","--volumes","--remove-orphans","--timeout","30",timeout=120)
                except Exception:cleanup_ok = False
            retain_image = built and self.keep_image and success and cleanup_ok
            if built and not retain_image:
                try:self.command("image","rm",self.image,compose=False,timeout=60)
                except Exception:cleanup_ok = False
            self.report["image_retained"] = retain_image
            self.report["cleanup_passed"] = cleanup_ok
            self.report["passed"] = success and cleanup_ok
            folder = self.root/"reports"
            folder.mkdir(exist_ok=True)
            (folder/"container-runtime-verification.json").write_text(json.dumps(self.report,indent=2),encoding="utf-8")
        return self.report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true",help="Build/run isolated test containers and remove their volumes afterwards.")
    parser.add_argument("--keep-image",action="store_true",help="Retain the exact successful image for CI publication; test volumes are still removed.")
    parser.add_argument("--timeout",type=int,default=1800,help="Bootstrap/readiness timeout in seconds (120-7200).")
    args = parser.parse_args()
    if not 120 <= args.timeout <= 7200:
        parser.error("--timeout must be between 120 and 7200 seconds")
    if not args.run:
        print(json.dumps(validate_assets(),indent=2))
        print("Asset preflight only. Use --run when a local Linux Docker daemon is available.")
        return
    report = ContainerVerifier(timeout=args.timeout,keep_image=args.keep_image).run()
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["passed"] else 1)

if __name__ == "__main__":main()
