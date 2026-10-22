"""Download a pinned official ONNX NLI model with checked ranges and SHA-256."""
import concurrent.futures,hashlib,json,urllib.request
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1]
REPO="Xenova/nli-deberta-v3-xsmall"
REV="2a4f614a701367a02d51389039afc998faeda637"
SHA="3fac2500c45c75af42c7711de0d1b93d59577456100208be0dc1f9e8811946b6"
SIZE=87246587
def main():
    folder=ROOT/".cache"/"nli";folder.mkdir(exist_ok=True)
    target=folder/"model.onnx"
    if not target.exists():
        parts=folder/"parts";parts.mkdir(exist_ok=True)
        block=8*1024*1024
        def fetch(start):
            stop=min(SIZE,start+block)-1;p=parts/str(start)
            if p.exists() and p.stat().st_size==stop-start+1:return p
            req=urllib.request.Request(f"https://huggingface.co/{REPO}/resolve/{REV}/onnx/model_quantized.onnx?part={start}",headers={"Range":f"bytes={start}-{stop}"})
            with urllib.request.urlopen(req,timeout=90) as r:
                if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{stop}/{SIZE}":raise ValueError("Invalid range")
                data=r.read(stop-start+2)
            if len(data)!=stop-start+1:raise ValueError("Invalid part length")
            p.write_bytes(data);return p
        starts=list(range(0,SIZE,block))
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(fetch,starts))
        with target.open("wb") as out:
            for start in starts:out.write((parts/str(start)).read_bytes())
    if hashlib.file_digest(target.open("rb"),"sha256").hexdigest()!=SHA:raise ValueError("NLI model hash mismatch")
    assets={}
    for name in ("tokenizer.json","tokenizer_config.json","config.json"):
        p=folder/name
        if not p.exists():
            with urllib.request.urlopen(f"https://huggingface.co/{REPO}/resolve/{REV}/{name}",timeout=60) as r:p.write_bytes(r.read())
        assets[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (folder/"provenance.json").write_text(json.dumps({"repository":REPO,"revision":REV,"sha256":SHA,"bytes":SIZE,"assets":assets},indent=2),encoding="utf-8")
    print("Pinned NLI model verified.",flush=True)
if __name__=="__main__":main()
