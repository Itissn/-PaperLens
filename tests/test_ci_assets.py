import hashlib
import io
import pytest
from scripts.prepare_ci_assets import download_verified, prepare_assets


def test_download_checks_content_and_reuses_only_verified_bytes(tmp_path):
    data = b"GGUF-public-fixture"
    digest = hashlib.sha256(data).hexdigest()
    path = tmp_path / "model.gguf"
    calls = []
    def opened(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(data)
    download_verified("https://example.org/public.gguf", path, len(data), digest, opened)
    assert path.read_bytes() == data
    download_verified("https://example.org/public.gguf", path, len(data), digest,
                      lambda *a, **k: pytest.fail("Verified asset should be reused"))
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [b"wrong", b"expected plus oversized content"])
def test_bad_download_never_becomes_a_model(tmp_path, payload):
    path = tmp_path / "model.gguf"
    with pytest.raises(ValueError):
        download_verified("https://example.org/model", path, 8,
                          hashlib.sha256(b"expected").hexdigest(),
                          lambda *a, **k: io.BytesIO(payload))
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_corrupt_existing_file_is_preserved_and_fails_closed(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="existing"):
        download_verified("https://example.org/model", path, 7,
                          hashlib.sha256(b"correct").hexdigest())
    assert path.read_bytes() == b"corrupt"


def test_interrupted_download_removes_only_its_own_partial_file(tmp_path):
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            raise TimeoutError("network interrupted")
    path = tmp_path / "model.gguf"
    unrelated = tmp_path / "other.file"
    unrelated.write_text("keep")
    with pytest.raises(TimeoutError):
        download_verified("https://example.org/model", path, 4, "unused",
                          lambda *a, **k: Interrupted())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["other.file"]


def test_ci_credentials_are_generated_privately_and_never_replace_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.prepare_ci_assets.download_verified", lambda *a, **k: None)
    prepare_assets(tmp_path)
    key = tmp_path / ".cache/local-llm/api-key.txt"
    first = key.read_text()
    assert len(first.strip()) >= 32
    prepare_assets(tmp_path)
    assert key.read_text() == first
    assert first.strip() not in capsys.readouterr().out

def test_nli_setup_bootstraps_a_clean_clone_without_preexisting_cache(tmp_path, monkeypatch):
    from scripts import setup_nli
    data = b"onnx"
    monkeypatch.setattr(setup_nli, "ROOT", tmp_path)
    monkeypatch.setattr(setup_nli, "SIZE", len(data))
    monkeypatch.setattr(setup_nli, "SHA", hashlib.sha256(data).hexdigest())
    class Part(io.BytesIO):
        status = 206
        headers = {"Content-Range": "bytes 0-3/4"}
    def opened(request, timeout):
        if isinstance(request, str):
            return io.BytesIO(b"{}")
        return Part(data)
    monkeypatch.setattr(setup_nli.urllib.request, "urlopen", opened)
    setup_nli.main()
    folder = tmp_path / ".cache/nli"
    assert (folder / "model.onnx").read_bytes() == data
    assert (folder / "provenance.json").is_file()

def test_new_posix_secret_is_mount_readable_but_parent_directory_is_private(tmp_path, monkeypatch):
    import os
    import stat
    if os.name != "posix":
        return  # Windows access is controlled by ACLs, not POSIX mode bits.
    monkeypatch.setattr("scripts.prepare_ci_assets.download_verified", lambda *a, **k: None)
    prepare_assets(tmp_path)
    key = tmp_path / ".cache/local-llm/api-key.txt"
    assert stat.S_IMODE(key.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(key.stat().st_mode) == 0o644