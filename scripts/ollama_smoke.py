"""Real portable Ollama adapter test using the existing verified GGUF."""
import json,os,time,urllib.request
from pathlib import Path
from paperlens.store import Store
from paperlens.embeddings import Embedder
from paperlens.reranking import Reranker
from paperlens.retrieval import Retriever
from paperlens.answer import answer
ROOT=Path(__file__).resolve().parents[1]
def main():
    os.environ["PAPERLENS_OLLAMA_URL"]="http://127.0.0.1:11435"
    os.environ["PAPERLENS_OLLAMA_MODEL"]="paperlens-qwen"
    ranker=Reranker(ROOT/".cache/reranker")
    query="How many random seeds were used in the BN-GPGLS experiments?"
    hits=Retriever(Store(ROOT/"data"),Embedder(ROOT/".cache/embeddings"),ranker).search(query,k=5,rerank=True)["hits"]
    events=[];start=time.perf_counter()
    result=answer(query,hits,"ollama",ranker,lambda event,data:events.append({"event":event,"characters":len(data.get("text",""))}))
    report={"real_runtime":"Portable official Ollama v0.40.7, project-only files","question":query,"result":result,"events":events,"latency_ms":round((time.perf_counter()-start)*1000,2)}
    (ROOT/"reports/ollama-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="events"}),flush=True)
    assert result["status"]=="generated",result
    assert "30" in " ".join(p["text"] for p in result["paragraphs"])
    assert any(e["event"]=="draft" for e in events)
if __name__=="__main__":main()
