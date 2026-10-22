"""Container-only readiness. Probes never return keys, paths or exception details."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path

CONTRACT = "paperlens-container-v1"

def _marker_assets(root):
    root = Path(root).resolve()
    marker = json.loads((root/"data/container-bootstrap.json").read_text(encoding="utf-8"))
    if not isinstance(marker,dict) or marker.get("contract") != CONTRACT or not marker.get("assets"):
        raise ValueError("Incomplete bootstrap marker.")
    result = []
    cache = (root/".cache").resolve()
    for item in marker["assets"]:
        path = (root/item["path"]).resolve()
        if not path.is_relative_to(cache):
            raise ValueError("Invalid bootstrap asset.")
        if not path.is_file():
            raise ValueError("Missing bootstrap asset: "+item["path"])
        if not isinstance(item["bytes"], int) or item["bytes"] <= 0 or path.stat().st_size != item["bytes"]:
            raise ValueError("Changed bootstrap asset size: "+item["path"])
        result.append((path, item))
    return result

def marker_valid(root, verify_hashes=False):
    try:
        assets = _marker_assets(root)
        if verify_hashes:
            for path, item in assets:
                with path.open("rb") as source:
                    if hashlib.file_digest(source,"sha256").hexdigest() != item["sha256"]:
                        return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False

def write_marker(root, assets):
    root = Path(root).resolve()
    records = []
    for asset in sorted({Path(p).resolve() for p in assets}):
        if not asset.is_relative_to((root/".cache").resolve()) or not asset.is_file():
            raise ValueError("Bootstrap assets must belong to the cache volume.")
        with asset.open("rb") as source:
            digest = hashlib.file_digest(source,"sha256").hexdigest()
        records.append({"path":asset.relative_to(root).as_posix(),"bytes":asset.stat().st_size,"sha256":digest})
    if not records or any(r["bytes"] <= 0 for r in records):
        raise ValueError("Bootstrap asset inventory is empty or incomplete.")
    folder = root/"data"
    folder.mkdir(parents=True,exist_ok=True)
    temp = folder/"container-bootstrap.json.tmp"
    temp.write_text(json.dumps({"contract":CONTRACT,"assets":records},indent=2),encoding="utf-8")
    temp.replace(folder/"container-bootstrap.json")

def index_ready(store):
    docs = store.documents()
    return bool(docs) and all(d["chunks"] > 0 and d["embedded_chunks"] == d["chunks"] for d in docs)

def probe_model():
    try:
        key = Path(os.environ["PAPERLENS_LLM_KEY_FILE"]).read_text(encoding="utf-8").strip()
        if not key:
            return False
        url = os.environ["PAPERLENS_LLM_BASE_URL"].rstrip("/") + "/health"
        request = urllib.request.Request(url,headers={"Authorization":"Bearer "+key})
        with urllib.request.urlopen(request,timeout=1.5) as response:
            health = json.loads(response.read(4096))
            if response.status != 200 or not isinstance(health,dict) or health.get("status") != "ok":
                return False
        # llama.cpp may expose /health publicly; check authenticated model discovery too.
        request = urllib.request.Request(os.environ["PAPERLENS_LLM_BASE_URL"].rstrip("/")+"/v1/models",
                                         headers={"Authorization":"Bearer "+key})
        with urllib.request.urlopen(request,timeout=1.5) as response:
            models = json.loads(response.read(65536))
            if response.status != 200 or not isinstance(models,dict) or not isinstance(models.get("data"),list):
                return False
            return any(isinstance(m,dict) and m.get("id") == "paperlens-qwen" for m in models["data"])
    except (OSError, ValueError, KeyError):
        return False

def deployment_status(store, root, probe=None):
    checks = {"database":False,"bootstrap":False,"index":False,"administrator":False,"model":False}
    try:
        with store.connect() as con:
            checks["database"] = con.execute("SELECT 1").fetchone()[0] == 1
            checks["administrator"] = bool(con.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone())
        checks["index"] = index_ready(store)
        checks["bootstrap"] = marker_valid(root)
    except Exception:
        # Readiness is public; keep internal paths/schema/errors in neither body nor logs.
        pass
    checks["model"] = (probe or probe_model)()
    return {"ready":all(checks.values()),"checks":checks,"scope":"Deployment prerequisites, not an answer-accuracy test."}
