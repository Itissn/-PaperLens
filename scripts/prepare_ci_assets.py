"""Prepare pinned public inference assets for isolated CI; never prints credentials."""
import hashlib
import os
import secrets
import urllib.request
import uuid
from pathlib import Path
from scripts.container_preflight import ROOT, MODEL_FILE, MODEL_BYTES, MODEL_SHA256

MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/"
    "7dabda4d13d513e3e842b20f0d435c732f172cbe/qwen2.5-3b-instruct-q4_k_m.gguf"
)


def verified(path, size, digest):
    if not path.is_file() or path.stat().st_size != size:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == digest


def download_verified(url, path, size, digest, opener=urllib.request.urlopen):
    path = Path(path)
    if path.exists():
        if not verified(path, size, digest):
            raise ValueError("The existing model failed verification; it has not been replaced.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".download-" + uuid.uuid4().hex)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PaperLens-CI/1.0"})
        total = 0
        with opener(request, timeout=120) as response, partial.open("xb") as target:
            while block := response.read(min(1024 * 1024, size - total + 1)):
                total += len(block)
                if total > size:
                    raise ValueError("Model download exceeded its pinned size.")
                target.write(block)
        if not verified(partial, size, digest):
            raise ValueError("Model download failed its pinned size or SHA256 check.")
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def prepare_assets(root=ROOT):
    root = Path(root)
    download_verified(MODEL_URL, root / MODEL_FILE, MODEL_BYTES, MODEL_SHA256)
    key = root / ".cache/local-llm/api-key.txt"
    key.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass  # Preserve local credentials when a developer runs this script.
    else:
        # Compose file secrets are bind mounts: UID 10001 must read the file.
        # A private host directory prevents other host users from traversing it.
        if os.name == "posix":
            key.parent.chmod(0o700)
            os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="ascii") as output:
            output.write(secrets.token_urlsafe(48) + "\n")
    print("Pinned public model verified; private model key is available.", flush=True)


if __name__ == "__main__":
    prepare_assets()