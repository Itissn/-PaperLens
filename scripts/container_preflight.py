"""Read-only host checks. No installers, system changes or Docker daemon calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILE = ".cache/local-llm/qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_BYTES = 2104932768
MODEL_SHA256 = "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"

class PreflightError(ValueError):
    pass

def validate_assets(root=ROOT, env=None):
    env = os.environ if env is None else env
    root = Path(root)
    model = Path(env.get("PAPERLENS_GGUF_FILE") or MODEL_FILE)
    key_file = Path(env.get("PAPERLENS_LLM_KEY_FILE_HOST") or ".cache/local-llm/api-key.txt")
    if not model.is_absolute():model = root/model
    if not key_file.is_absolute():key_file = root/key_file
    if not model.is_file() or model.stat().st_size != MODEL_BYTES:
        raise PreflightError("The Qwen 3B GGUF is missing or has an unexpected size. Run scripts/setup_model_3b.py first.")
    with model.open("rb") as source:
        if hashlib.file_digest(source,"sha256").hexdigest() != MODEL_SHA256:
            raise PreflightError("The Qwen 3B GGUF checksum does not match the pinned public model.")
    try:key = key_file.read_text(encoding="utf-8").strip()
    except OSError:raise PreflightError("The model key file is missing. Create a private random key file before starting Compose.") from None
    if not 32 <= len(key) <= 256 or any(not c.isascii() or c.isspace() or not c.isprintable() for c in key):
        raise PreflightError("The model key file must contain one 32-256 character ASCII token.")
    try:port = int(env.get("PAPERLENS_PORT") or "8767")
    except ValueError:raise PreflightError("PAPERLENS_PORT must be a port number.") from None
    if not 1 <= port <= 65535:raise PreflightError("PAPERLENS_PORT must be between 1 and 65535.")
    return {"model_verified":True,"model_sha256":MODEL_SHA256,"key_file_valid":True,"host_port":port,"runtime_tested":False}

def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:print(json.dumps(validate_assets(),indent=2))
    except (OSError,PreflightError) as exc:
        if isinstance(exc,PreflightError):raise SystemExit(str(exc)) from None
        raise SystemExit("Host asset check failed. Check file permissions and available storage.") from None

if __name__ == "__main__":main()
