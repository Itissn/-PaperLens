"""Fixed official portable model assets; local-only, no paid API."""
import hashlib,json,urllib.request,zipfile
from pathlib import Path
import paperlens
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/".cache"/"local-llm"
ASSETS.mkdir(parents=True,exist_ok=True)
TAG="b11763"
REV="91cad51170dc346986eccefdc2dd33a9da36ead9"
MODEL="qwen2.5-1.5b-instruct-q4_k_m.gguf"
def download(url,path):
    if path.exists(): return
    temp=path.with_suffix(path.suffix+".part")
    with urllib.request.urlopen(url,timeout=120) as response,temp.open("wb") as out:
        while block:=response.read(1024*1024):out.write(block)
    temp.replace(path)
    print(path.name,path.stat().st_size,flush=True)
def main():
    zip_path=ASSETS/("llama-"+TAG+".zip")
    binary_url=f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/llama-{TAG}-bin-win-cpu-x64.zip"
    download(binary_url,zip_path)
    binaries=ASSETS/"bin";binaries.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as package:
        for item in package.infolist():
            target=(binaries/item.filename).resolve()
            if not target.is_relative_to(binaries.resolve()):raise ValueError("Unsafe archive entry")
        package.extractall(binaries)
    model_url=f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{REV}/{MODEL}"
    download(model_url,ASSETS/MODEL)
    tree_url=f"https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/{REV}"
    with urllib.request.urlopen(tree_url,timeout=60) as r:tree=json.load(r)
    expected=next(f["lfs"]["oid"] for f in tree if f["path"]==MODEL)
    digest=hashlib.file_digest((ASSETS/MODEL).open("rb"),"sha256").hexdigest()
    if digest!=expected:raise ValueError("Model hash mismatch; do not run.")
    result={"llama_release":TAG,"binary_url":binary_url,"binary_sha256":hashlib.file_digest(zip_path.open("rb"),"sha256").hexdigest(),"model_revision":REV,"model_url":model_url,"model_sha256":digest}
    (ASSETS/"provenance.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("Model hash verified.",flush=True)
if __name__=="__main__":main()
