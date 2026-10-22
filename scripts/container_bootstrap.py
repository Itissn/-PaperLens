"""Idempotent container-volume setup. No account credentials are accepted here."""
import subprocess
import hashlib
import json
import uuid
import sys
from pathlib import Path
from paperlens.deployment import marker_valid, write_marker, index_ready
from paperlens.store import Store

ROOT = Path(__file__).resolve().parents[1]

def pinned_assets(root):
    pins = json.loads(Path(__file__).with_name("container-assets.json").read_text(encoding="utf-8"))
    for name,digest in pins.items():
        path = (Path(root)/name).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError("Pinned asset path escaped the project.")
        yield path,digest

def repair_pinned_assets(root):
    """Quarantine corrupted/partial files, preserving them for inspection."""
    for path,digest in pinned_assets(root):
        if not path.is_file():
            continue
        with path.open("rb") as source:
            intact = hashlib.file_digest(source,"sha256").hexdigest() == digest
        if not intact:
            path.rename(path.with_name(path.name+".invalid-"+uuid.uuid4().hex[:8]))
            if path.is_relative_to((Path(root)/".cache").resolve()):
                candidates = {path.parent/"parts"}
                if path.parent.name == "onnx":
                    candidates.add(path.parent.parent/"parts")
                for parts in candidates:
                    if parts.is_dir():
                        parts.rename(parts.with_name("parts-invalid-"+uuid.uuid4().hex[:8]))

def verify_pinned_assets(root):
    for path,digest in pinned_assets(root):
        with path.open("rb") as source:
            if hashlib.file_digest(source,"sha256").hexdigest() != digest:
                raise RuntimeError("A downloaded public asset failed its pinned checksum.")

def bootstrap(root=ROOT):
    root = Path(root)
    store = Store(root/"data")
    if marker_valid(root,verify_hashes=True) and index_ready(store):
        print("Container assets and complete index already verified.",flush=True)
        return
    marker = root/"data/container-bootstrap.json"
    marker.unlink(missing_ok=True)
    # A failed phase leaves no success marker; rerunning repairs/reuses downloaded files.
    from scripts.download_corpus import main as corpus
    from scripts.setup_reranker import main as reranker
    from scripts.setup_nli import main as nli
    repair_pinned_assets(root)
    corpus()
    reranker()
    nli()
    verify_pinned_assets(root)
    subprocess.run([sys.executable,"manage.py","index"],cwd=root,check=True)
    from paperlens.embeddings import Embedder
    from paperlens.reranking import Reranker
    from paperlens.semantic import SemanticVerifier
    from rapidocr_onnxruntime import RapidOCR
    embedder = Embedder(root/".cache/embeddings")
    if len(embedder.query("vehicle routing")) != 384:
        raise RuntimeError("Embedding warm-up failed.")
    if len(Reranker(root/".cache/reranker").score("routing",["A vehicle routing study."])) != 1:
        raise RuntimeError("Reranker warm-up failed.")
    if not SemanticVerifier(root/".cache/nli").predict("A vehicle moves.","A vehicle moves."):
        raise RuntimeError("NLI warm-up failed.")
    RapidOCR()  # Load the package's CPU OCR models before declaring setup complete.
    if not index_ready(store):
        raise RuntimeError("The public-paper index is incomplete.")
    assets = [p for p in (root/".cache").rglob("*") if p.is_file() and p.stat().st_size > 0 and not any(part.startswith(("parts",".locks")) or ".invalid-" in part for part in p.parts)]
    write_marker(root,assets)
    print("Container bootstrap completed; assets, CPU inference and index checked.",flush=True)

def main():
    try:bootstrap()
    except Exception:
        print("Container bootstrap failed; no completion marker was written. Check network/storage and rerun bootstrap.",file=sys.stderr,flush=True)
        raise

if __name__ == "__main__":main()
