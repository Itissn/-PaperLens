"""Pinned portable Ollama. No installer, service, registry or system PATH changes."""
import concurrent.futures,hashlib,json,urllib.request,zipfile
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/".cache/ollama"
TAG="v0.40.7";SIZE=1582514985;SHA="e6527768c53e85ec4596495fb0f035ef07f437b4b591ebc3581684699a4668f4"
URL=f"https://github.com/ollama/ollama/releases/download/{TAG}/ollama-windows-amd64.zip"
def main():
    FOLDER.mkdir(exist_ok=True);target=FOLDER/"runtime.zip";parts=FOLDER/"parts";parts.mkdir(exist_ok=True)
    if not target.exists():
        block=16*1024*1024;starts=list(range(0,SIZE,block))
        def fetch(start):
            end=min(start+block,SIZE)-1;p=parts/str(start)
            if p.exists() and p.stat().st_size==end-start+1:return
            for attempt in range(3):
                try:
                    req=urllib.request.Request(URL+f"?part={start}",headers={"Range":f"bytes={start}-{end}","User-Agent":"PaperLens"})
                    with urllib.request.urlopen(req,timeout=90) as r:
                        if r.status!=206 or r.headers.get("Content-Range")!=f"bytes {start}-{end}/{SIZE}":raise ValueError("Range not honoured")
                        value=r.read(end-start+2)
                    if len(value)!=end-start+1:raise ValueError("Invalid range length")
                    p.write_bytes(value);return
                except Exception:
                    if attempt==2:raise
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for i,_ in enumerate(pool.map(fetch,starts),1):
                if i%10==0:print(f"Ollama portable download {i}/{len(starts)}",flush=True)
        with target.open("wb") as out:
            for start in starts:out.write((parts/str(start)).read_bytes())
    digest=hashlib.file_digest(target.open("rb"),"sha256").hexdigest()
    if digest!=SHA:raise ValueError("Portable runtime hash mismatch")
    binary=FOLDER/"bin";binary.mkdir(exist_ok=True)
    with zipfile.ZipFile(target) as archive:
        for entry in archive.infolist():
            name=entry.filename.replace("\\","/")
            if name.endswith("/") or any(part.lower().startswith(("cuda","rocm","vulkan","mlx")) for part in Path(name).parts):continue
            if not (name=="ollama.exe" or name.startswith("lib/ollama/")):continue
            path=(binary/name).resolve()
            if not path.is_relative_to(binary.resolve()):raise ValueError("Unsafe archive member")
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(entry) as src,path.open("wb") as dst:
                import shutil
                shutil.copyfileobj(src,dst)
    (FOLDER/"provenance.json").write_text(json.dumps({"tag":TAG,"url":URL,"sha256":SHA,"bytes":SIZE,"installation":"Portable project files only; no service"},indent=2))
    for start in range(0,SIZE,16*1024*1024):(parts/str(start)).unlink(missing_ok=True)
    print("Official portable Ollama verified.",flush=True)
if __name__=="__main__":main()
