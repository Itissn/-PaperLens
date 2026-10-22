"""Download only fixed, public versions. Existing PDFs are checksum recorded."""
import hashlib, json, time, urllib.request
import paperlens
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CORPUS = [
    {"arxiv_id":"2505.15839v1","title":"Curriculum Learning in Genetic Programming Guided Local Search for Large-scale Vehicle Routing Problems","status":"Public arXiv version of CEC 2025 paper"},
    {"arxiv_id":"2609.24105v1","title":"DCL-GPGLS: Dynamic Curriculum Learning for Genetic Programming Guided Local Search in Large-Scale Vehicle Routing","status":"arXiv preprint"},
    {"arxiv_id":"2609.24104v1","title":"Genetic Programming with Behaviour-based Niching for Learning Guided Local Search in Vehicle Routing Problems","status":"arXiv preprint"},
]
def main():
    folder=ROOT/"data"/"papers"; folder.mkdir(parents=True,exist_ok=True)
    for paper in CORPUS:
        path=folder/(paper["arxiv_id"]+".pdf")
        url="https://arxiv.org/pdf/"+paper["arxiv_id"]
        if not path.exists():
            req=urllib.request.Request(url,headers={"User-Agent":"PaperLens/0.1 (personal academic learning)"})
            with urllib.request.urlopen(req,timeout=90) as response:
                data=response.read(20*1024*1024+1)
            if not data.startswith(b"%PDF") or len(data)>20*1024*1024:
                raise ValueError("Not a bounded PDF: "+url)
            path.write_bytes(data)
            time.sleep(1)
        paper.update(file=path.name,source_url="https://arxiv.org/abs/"+paper["arxiv_id"],sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        print(paper["arxiv_id"],path.stat().st_size)
    (folder/"manifest.json").write_text(json.dumps(CORPUS,indent=2),encoding="utf-8")
if __name__=="__main__": main()
