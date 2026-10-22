import json
import subprocess
import pytest
from scripts.verify_container import ContainerVerifier,read_events,assert_agent_result,VerificationFailure

def test_sse_requires_terminal_result_and_rejects_application_errors():
    with pytest.raises(VerificationFailure,match="without a result"):
        read_events(["event: draft",'data: {"text":"partial"}'])
    with pytest.raises(VerificationFailure,match="application error"):
        read_events(["event: error",'data: {"message":"failure"}'])
    events,result=read_events(["event: draft",'data: {"text":"streamed"}',"event: result",'data: {"status":"generated"}'])
    assert events==["draft","result"] and result["status"]=="generated"

def test_inference_check_does_not_count_an_abstention_or_no_tool_calls_as_success():
    with pytest.raises(VerificationFailure):
        assert_agent_result(["draft"],{"status":"abstained"})
    result={"status":"generated","paragraphs":[{"text":"30 seeds."}],
            "semantic_check":{"passed":True},"validation":{"passed":True},
            "citations":[{"page":8}],"agent":{"all_cited_pages_read":True,"tool_calls":2,"trace":[
                {"tool":"search_papers","outcome":"ok"},{"tool":"read_page","outcome":"ok"}]}}
    assert_agent_result(["draft"],result)
    with pytest.raises(VerificationFailure):
        assert_agent_result([],result)

def test_failed_bootstrap_cleans_only_the_generated_project_and_redacts_errors(tmp_path):
    calls=[]
    private="PRIVATE_FAILURE_VALUE"
    def runner(command,**kwargs):
        calls.append((command,kwargs))
        if command[1:3]==["context","inspect"]:out="npipe:////./pipe/docker_engine"
        elif command[1:2]==["version"]:out="linux"
        elif command[-1:] == ["bootstrap"]:raise RuntimeError(private)
        else:out=""
        return subprocess.CompletedProcess(command,0,stdout=out)
    verifier=ContainerVerifier(tmp_path,runner=runner,asset_check=lambda *args:None)
    report=verifier.run()
    assert not report["passed"] and report["runtime_tested"] and report["cleanup_passed"]
    assert report["failure"]["phase"]=="corpus model and index bootstrap"
    assert private not in json.dumps(report)
    cleanup=[c for c,k in calls if "down" in c][0]
    assert cleanup[cleanup.index("--project-name")+1] == verifier.project
    assert verifier.project.startswith("paperlens-verify-") and "--volumes" in cleanup
    create=[(c,k) for c,k in calls if "--password-stdin" in c][0]
    assert create[1]["input"].strip() not in " ".join(create[0])
    assert all(k["env"]["PAPERLENS_APP_IMAGE"]==verifier.image for c,k in calls)

def test_remote_context_rejected_before_any_container_mutation(tmp_path):
    calls=[]
    def runner(command,**kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command,0,stdout="ssh://external.example")
    verifier=ContainerVerifier(tmp_path,runner=runner,asset_check=lambda *args:None)
    verifier.env.pop("DOCKER_HOST",None)
    report=verifier.run()
    assert not report["passed"] and not report["runtime_tested"]
    assert all("run" not in c and "up" not in c and "down" not in c for c in calls)

def test_cleanup_failure_cannot_be_reported_as_a_pass(tmp_path,monkeypatch):
    def runner(command,**kwargs):
        if "down" in command:raise RuntimeError("cleanup failure")
        out="linux" if command[1:2]==["version"] else "unix:///var/run/docker.sock" if command[1:3]==["context","inspect"] else ""
        return subprocess.CompletedProcess(command,0,stdout=out)
    verifier=ContainerVerifier(tmp_path,runner=runner,asset_check=lambda *args:None)
    verifier.env.pop("DOCKER_HOST",None)
    monkeypatch.setattr(verifier,"check_api",lambda password:None)
    report=verifier.run()
    assert not report["cleanup_passed"] and not report["passed"]


def test_ci_can_retain_exact_successful_image_but_not_test_volumes(tmp_path, monkeypatch):
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        out = "linux" if command[1:2] == ["version"] else "unix:///var/run/docker.sock" if command[1:3] == ["context", "inspect"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=out)
    verifier = ContainerVerifier(tmp_path, runner=runner, asset_check=lambda *args: None, keep_image=True)
    verifier.env.pop("DOCKER_HOST", None)
    monkeypatch.setattr(verifier, "check_api", lambda password: None)
    report = verifier.run()
    assert report["passed"] and report["image_retained"] and report["image"] == verifier.image
    assert any("down" in c and "--volumes" in c for c in calls)
    assert not any(c[1:3] == ["image", "rm"] for c in calls)


def test_ci_cleanup_failure_removes_image_and_prevents_publication(tmp_path, monkeypatch):
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if "down" in command:
            raise RuntimeError("cleanup failure")
        out = "linux" if command[1:2] == ["version"] else "unix:///var/run/docker.sock" if command[1:3] == ["context", "inspect"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=out)
    verifier = ContainerVerifier(tmp_path, runner=runner, asset_check=lambda *args: None, keep_image=True)
    verifier.env.pop("DOCKER_HOST", None)
    monkeypatch.setattr(verifier, "check_api", lambda password: None)
    report = verifier.run()
    assert not report["passed"] and not report["image_retained"]
    assert any(c[1:3] == ["image", "rm"] for c in calls)