"""Download a fixed official 3B comparison model; no system installation."""
import concurrent.futures,hashlib,json,time,urllib.request
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1]
REPO="Qwen/Qwen2.5-3B-Instruct-GGUF"
FILE="qwen2.5-3b-instruct-q4_k_m.gguf"
def get_json(url):
    with urllib.request.urlopen(url,timeout=60) as r:return json.load(r)
def main():
    info=get_json("https://huggingface.co/api/models/"+REPO);revision=info["sha"]
    tree=get_json(f"https://huggingface.co/api/models/{REPO}/tree/{revision}")
    item=next(x for x in tree if x["path"]==FILE)
    folder=ROOT/".cache"/"local-llm";parts=folder/"3b-parts";parts.mkdir(exist_ok=True)
    target=folder/FILE;total=item["size"];expected=item["lfs"]["oid"]
    if not target.exists():
        block=16*1024*1024;starts=list(range(0,total,block))
        def fetch(start):
            end=min(start+block,total)-1;path=parts/str(start)
            if path.exists() and path.stat().st_size==end-start+1:return
            for attempt in range(3):
                try:
                    req=urllib.request.Request(f"https://huggingface.co/{REPO}/resolve/{revision}/{FILE}?part={start}",headers={"Range":f"bytes={start}-{end}"})
                    with urllib.request.urlopen(req,timeout=90) as r:
                        if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{total}":raise ValueError("Invalid range")
                        data=r.read(end-start+2)
                    if len(data)!=end-start+1:raise ValueError("Incomplete range")
                    path.write_bytes(data);return
                except Exception:
                    if attempt==2:raise
                    time.sleep(attempt+1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            for n,_ in enumerate(pool.map(fetch,starts),1):
                if n%12==0:print(f"3B comparison model: {n}/{len(starts)} ranges",flush=True)
        with target.open("wb") as out:
            for start in starts:out.write((parts/str(start)).read_bytes())
        for start in starts:(parts/str(start)).unlink()
    with target.open("rb") as src:digest=hashlib.file_digest(src,"sha256").hexdigest()
    if digest!=expected:raise ValueError("Model hash mismatch.")
    provenance={"repository":REPO,"revision":revision,"file":FILE,"sha256":digest,"bytes":total,"license":"qwen-research","purpose":"Local research and learning comparison"}
    (folder/"3b-provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    print("3B model verified.",flush=True)
if __name__=="__main__":main()
