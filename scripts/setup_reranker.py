"""Verified, resumable official cross-encoder download for Windows proxy networks."""
import concurrent.futures,hashlib,json,shutil,urllib.request
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1]
REPO="Xenova/ms-marco-MiniLM-L-6-v2"
REV="a09144355adeed5f58c8ed011d209bf8ee5a1fec"
def main():
    folder=ROOT/".cache"/"reranker"/"verified-model"
    folder.mkdir(parents=True,exist_ok=True)
    def read_json(url):
        with urllib.request.urlopen(url,timeout=60) as r:return json.load(r)
    files=read_json(f"https://huggingface.co/api/models/{REPO}/tree/{REV}/onnx")
    info=next(f for f in files if f["path"]=="onnx/model.onnx")
    total=info["size"];expected=info["lfs"]["oid"]
    path=folder/"onnx"/"model.onnx";path.parent.mkdir(exist_ok=True)
    if not path.exists() or path.stat().st_size!=total:
        parts=folder/"parts";parts.mkdir(exist_ok=True)
        block=8*1024*1024
        starts=list(range(0,total,block))
        def fetch(start):
            stop=min(total,start+block)-1
            target=parts/str(start)
            if target.exists() and target.stat().st_size==stop-start+1:return
            req=urllib.request.Request(f"https://huggingface.co/{REPO}/resolve/{REV}/onnx/model.onnx?part={start}",headers={"Range":f"bytes={start}-{stop}"})
            with urllib.request.urlopen(req,timeout=90) as r:
                if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{stop}/{total}":raise ValueError("Range not honoured")
                data=r.read(stop-start+2)
            if len(data)!=stop-start+1:raise ValueError("Truncated model range")
            target.write_bytes(data)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for n,_ in enumerate(pool.map(fetch,starts),1):print(f"Reranker ranges {n}/{len(starts)}",flush=True)
        with path.open("wb") as out:
            for start in starts:out.write((parts/str(start)).read_bytes())
        for start in starts:(parts/str(start)).unlink()
    with path.open("rb") as source:actual=hashlib.file_digest(source,"sha256").hexdigest()
    if actual!=expected:raise ValueError("Model checksum mismatch")
    for name in ["config.json","tokenizer.json","tokenizer_config.json","special_tokens_map.json"]:
        cached=ROOT/".cache"/"reranker"/"models--Xenova--ms-marco-MiniLM-L-6-v2"/"snapshots"/REV/name
        if cached.exists():shutil.copy2(cached,folder/name)
        else:
            with urllib.request.urlopen(f"https://huggingface.co/{REPO}/resolve/{REV}/{name}",timeout=60) as r:(folder/name).write_bytes(r.read())
    (folder/"provenance.json").write_text(json.dumps({"repository":REPO,"revision":REV,"onnx_sha256":actual,"bytes":total},indent=2),encoding="utf-8")
    print("Reranker hash verified.",flush=True)
if __name__=="__main__":main()
