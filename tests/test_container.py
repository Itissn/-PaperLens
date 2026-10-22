import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from paperlens.store import Store
from paperlens.auth import Auth
from paperlens.api import create_app
from paperlens.deployment import deployment_status
from scripts.container_preflight import validate_assets, PreflightError
from scripts.container_bootstrap import write_marker, marker_valid
from test_api import FakeEmbedder, make_pdf
from paperlens.ingest import ingest_bytes, embed_pending

def prepared(tmp_path):
    store=Store(tmp_path/"data")
    Auth(store,True).create_user("admin","FixturePassword123!","admin")
    ingest_bytes(store,make_pdf(),"Fixture paper")
    embed_pending(store,FakeEmbedder())
    asset=tmp_path/".cache"/"fixture.onnx"
    asset.parent.mkdir();asset.write_bytes(b"fixture-model")
    write_marker(tmp_path,[asset])
    return store,asset

def test_readiness_rejects_missing_bootstrap_and_admin(tmp_path):
    status=deployment_status(Store(tmp_path/"data"),tmp_path,probe=lambda:True)
    assert not status["ready"] and not status["checks"]["bootstrap"]
    assert not status["checks"]["administrator"]

def test_readiness_rejects_broken_assets_index_or_model(tmp_path):
    store,asset=prepared(tmp_path)
    assert deployment_status(store,tmp_path,probe=lambda:True)["ready"]
    assert not deployment_status(store,tmp_path,probe=lambda:False)["checks"]["model"]
    asset.write_bytes(b"broken")
    assert not deployment_status(store,tmp_path,probe=lambda:True)["checks"]["bootstrap"]
    write_marker(tmp_path,[asset])
    with store.connect() as con:con.execute("UPDATE chunks SET vector=NULL")
    assert not deployment_status(store,tmp_path,probe=lambda:True)["checks"]["index"]

def test_invalid_marker_cannot_escape_cache(tmp_path):
    store,asset=prepared(tmp_path)
    marker=tmp_path/"data/container-bootstrap.json"
    body=json.loads(marker.read_text())
    body["assets"][0]["path"]="../private"
    marker.write_text(json.dumps(body))
    assert not marker_valid(tmp_path)

def test_readiness_endpoint_is_strict_only_when_requested(tmp_path,monkeypatch):
    client=TestClient(create_app(tmp_path,FakeEmbedder(),auth_required=True))
    assert client.get("/api/readiness").status_code==200
    monkeypatch.setenv("PAPERLENS_STRICT_READINESS","1")
    with patch("paperlens.deployment.probe_model",return_value=False):
        response=client.get("/api/readiness")
    assert response.status_code==503 and not response.json()["ready"]
    assert client.get("/api/health").status_code==200

def test_preflight_rejects_missing_or_wrong_model_without_reading_secret(tmp_path):
    with pytest.raises(PreflightError,match="GGUF"):
        validate_assets(tmp_path,{})
    model=tmp_path/".cache/local-llm/qwen2.5-3b-instruct-q4_k_m.gguf"
    model.parent.mkdir(parents=True);model.write_bytes(b"invalid")
    key=model.parent/"api-key.txt";key.write_text("DO-NOT-PRINT-THIS-PRIVATE-KEY-"*2)
    with pytest.raises(PreflightError,match="GGUF") as error:
        validate_assets(tmp_path,{})
    assert "PRIVATE" not in str(error.value)

def test_model_probe_uses_secret_file_and_fails_closed(tmp_path,monkeypatch):
    from paperlens.deployment import probe_model
    key=tmp_path/"key";key.write_text("private-fixture")
    monkeypatch.setenv("PAPERLENS_LLM_KEY_FILE",str(key))
    monkeypatch.setenv("PAPERLENS_LLM_BASE_URL","http://llm:8766")
    with patch("urllib.request.urlopen",side_effect=TimeoutError):
        assert not probe_model()

def test_bootstrap_reuses_verified_assets_without_network(tmp_path):
    from scripts.container_bootstrap import bootstrap
    store,asset=prepared(tmp_path)
    with patch("scripts.download_corpus.main",side_effect=AssertionError("No network expected")):
        bootstrap(tmp_path)
    assert marker_valid(tmp_path,verify_hashes=True)

def test_failed_bootstrap_removes_success_marker_and_retry_can_complete(tmp_path):
    from scripts.container_bootstrap import bootstrap
    store,asset=prepared(tmp_path)
    asset.write_bytes(b"changed")
    with patch("scripts.container_bootstrap.repair_pinned_assets"),patch("scripts.download_corpus.main",side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError,match="interrupted"):
            bootstrap(tmp_path)
    assert not (tmp_path/"data/container-bootstrap.json").exists()
    class Encoder:
        def query(self,text):return [0.0]*384
    class Ranker:
        def score(self,*args):return [1.0]
    class Verifier:
        def predict(self,*args):return {"entailment":1.0}
    with patch("scripts.container_bootstrap.repair_pinned_assets"),patch("scripts.container_bootstrap.verify_pinned_assets"), \
         patch("scripts.download_corpus.main"),patch("scripts.setup_reranker.main"),patch("scripts.setup_nli.main"), \
         patch("subprocess.run"),patch("paperlens.embeddings.Embedder",return_value=Encoder()), \
         patch("paperlens.reranking.Reranker",return_value=Ranker()), \
         patch("paperlens.semantic.SemanticVerifier",return_value=Verifier()),patch("rapidocr_onnxruntime.RapidOCR"):
        bootstrap(tmp_path)
    assert marker_valid(tmp_path,verify_hashes=True)

def test_corrupt_download_quarantined_and_checksum_failure_is_explicit(tmp_path):
    import hashlib
    from scripts.container_bootstrap import repair_pinned_assets,verify_pinned_assets
    asset=tmp_path/"fixture.onnx";asset.write_bytes(b"broken")
    pins=[(asset,hashlib.sha256(b"correct").hexdigest())]
    with patch("scripts.container_bootstrap.pinned_assets",return_value=iter(pins)):
        repair_pinned_assets(tmp_path)
    assert not asset.exists() and list(tmp_path.glob("fixture.onnx.invalid-*"))[0].read_bytes()==b"broken"
    asset.write_bytes(b"broken")
    with patch("scripts.container_bootstrap.pinned_assets",return_value=iter(pins)):
        with pytest.raises(RuntimeError,match="checksum"):
            verify_pinned_assets(tmp_path)

def test_compose_security_and_startup_contract():
    import yaml
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    config=yaml.safe_load((root/"compose.yaml").read_text(encoding="utf-8"))
    app=config["services"]["paperlens"];model=config["services"]["llm"]
    assert app["ports"]==["127.0.0.1:${PAPERLENS_PORT:-8767}:8765"]
    assert "ports" not in model
    assert app["depends_on"]["bootstrap"]["condition"]=="service_completed_successfully"
    assert app["read_only"] and app["cap_drop"]==["ALL"]
    assert model["volumes"][0]["read_only"] and not model["volumes"][0]["bind"]["create_host_path"]
    assert config["secrets"]["llm_key"]["file"].endswith("api-key.txt}")
    dockerfile=(root/"Dockerfile").read_text()
    assert "USER 10001:10001" in dockerfile
    assert "COPY scripts ./scripts" not in dockerfile

def test_marker_hash_detects_same_size_corruption(tmp_path):
    store,asset=prepared(tmp_path)
    asset.write_bytes(b"x"*asset.stat().st_size)
    assert marker_valid(tmp_path)
    assert not marker_valid(tmp_path,verify_hashes=True)

def test_model_probe_checks_authenticated_alias_after_public_health(tmp_path,monkeypatch):
    import io
    from paperlens.deployment import probe_model
    key=tmp_path/"key";key.write_text("private-fixture")
    monkeypatch.setenv("PAPERLENS_LLM_KEY_FILE",str(key))
    monkeypatch.setenv("PAPERLENS_LLM_BASE_URL","http://llm:8766")
    class Response(io.BytesIO):
        status=200
    seen=[]
    def opened(request,timeout):
        seen.append(request)
        return Response(b'{"status":"ok"}' if request.full_url.endswith("/health") else b'{"data":[{"id":"paperlens-qwen"}]}')
    with patch("urllib.request.urlopen",side_effect=opened):
        assert probe_model()
    assert len(seen)==2 and seen[1].get_header("Authorization")=="Bearer private-fixture"
    with patch("urllib.request.urlopen",side_effect=[Response(b'{"status":"ok"}'),Response(b'{"data":[{"id":"wrong-model"}]}')]):
        assert not probe_model()

def test_corrupted_json_marker_shape_is_not_ready(tmp_path):
    store,asset=prepared(tmp_path)
    (tmp_path/"data/container-bootstrap.json").write_text("[]")
    assert not marker_valid(tmp_path)

def test_malformed_model_json_is_not_ready(tmp_path,monkeypatch):
    import io
    from paperlens.deployment import probe_model
    key=tmp_path/"key";key.write_text("private-fixture")
    monkeypatch.setenv("PAPERLENS_LLM_KEY_FILE",str(key))
    monkeypatch.setenv("PAPERLENS_LLM_BASE_URL","http://llm:8766")
    class Response(io.BytesIO):
        status=200
    for payloads in ([b"[]"],[b'{"status":"ok"}',b'{"data":null}']):
        with patch("urllib.request.urlopen",side_effect=[Response(x) for x in payloads]):
            assert not probe_model()
