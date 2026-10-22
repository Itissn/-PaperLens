"""Resume a large official model download with validated HTTP byte ranges."""
import concurrent.futures,hashlib,json,time,urllib.request
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/".cache"/"local-llm"
MODEL="qwen2.5-1.5b-instruct-q4_k_m.gguf"
REV="91cad51170dc346986eccefdc2dd33a9da36ead9"
BASE=f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{REV}/{MODEL}"
TOTAL=1117320736
BLOCK=16*1024*1024
def main():
    parts=ASSETS/"chunks";parts.mkdir(exist_ok=True)
    def fetch(start):
        end=min(start+BLOCK,TOTAL)-1
        path=parts/str(start)
        if path.exists() and path.stat().st_size==end-start+1:return path
        for attempt in range(3):
            try:
                request=urllib.request.Request(BASE+f"?download=true&part={start}",headers={"Range":f"bytes={start}-{end}"})
                with urllib.request.urlopen(request,timeout=60) as r:
                    if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{TOTAL}":
                        raise ValueError("Server did not honour bounded Range")
                    data=r.read(end-start+2)
                if len(data)!=end-start+1:raise ValueError("Incomplete range")
                path.write_bytes(data)
                return path
            except Exception:
                if attempt==2:raise
                time.sleep(1+attempt)
    starts=list(range(0,TOTAL,BLOCK))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for index,_ in enumerate(pool.map(fetch,starts),1):
            if index%8==0:print(f"Downloaded {index}/{len(starts)} ranges",flush=True)
    target=ASSETS/MODEL
    with target.open("wb") as out:
        for start in starts:out.write((parts/str(start)).read_bytes())
    with urllib.request.urlopen(f"https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/{REV}",timeout=30) as r:tree=json.load(r)
    expected=next(f["lfs"]["oid"] for f in tree if f["path"]==MODEL)
    with target.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
    if digest!=expected:raise ValueError("Hash mismatch")
    zip_path=ASSETS/"llama-b11763.zip"
    with zip_path.open("rb") as stream:binary_digest=hashlib.file_digest(stream,"sha256").hexdigest()
    provenance={"llama_release":"b11763","binary_url":"https://github.com/ggml-org/llama.cpp/releases/download/b11763/llama-b11763-bin-win-cpu-x64.zip","binary_sha256":binary_digest,"model_revision":REV,"model_url":BASE,"model_sha256":digest,"bytes":TOTAL}
    (ASSETS/"provenance.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    # Only exact task-generated files under the checked project cache.
    for start in starts:
        file=(parts/str(start)).resolve()
        if not file.is_relative_to(ASSETS.resolve()):raise ValueError("Unexpected cleanup path")
        file.unlink()
    stale=ASSETS/(MODEL+".part")
    if stale.exists() and stale.stat().st_size==0:stale.unlink()
    print("Official model complete; SHA-256 verified.",flush=True)
if __name__=="__main__":main()
