"""Real current-model generation and streaming; outputs retained for review."""
import json,time
from pathlib import Path
from paperlens.store import Store
from paperlens.embeddings import Embedder
from paperlens.reranking import Reranker
from paperlens.retrieval import Retriever
from paperlens.quality import expand_definitions
from paperlens.answer import answer
ROOT=Path(__file__).resolve().parents[1]
def main():
    store=Store(ROOT/"data");ranker=Reranker(ROOT/".cache/reranker")
    retriever=Retriever(store,Embedder(ROOT/".cache/embeddings"),ranker)
    cases=[]
    for question in ["How many random seeds were used in the BN-GPGLS experiments?","What are the six behaviour descriptors used by BN-GPGLS?"]:
        hits=retriever.search(question,k=8,rerank=True)["hits"]
        hits=expand_definitions(store,question,hits,ranker)
        events=[];start=time.perf_counter()
        def emit(event,data):
            events.append({"event":event,"characters":len(data.get("text","")),"at_ms":round((time.perf_counter()-start)*1000,2)})
        response=answer(question,hits,"local_llm",ranker,emit)
        case={"question":question,"response":response,"events":events}
        cases.append(case)
        print(json.dumps({"question":question,"status":response["status"],"paragraphs":response["paragraphs"],"completeness":response.get("completeness"),"semantic_check":response.get("semantic_check"),"stream_chunks":len([e for e in events if e["event"]=="draft"]),"pages":[h["page"] for h in hits]},ensure_ascii=True),flush=True)
        if "six behaviour" in question:
            (ROOT/"reports/v03-enumeration.json").write_text(json.dumps(case,indent=2),encoding="utf-8")
        (ROOT/"reports/v03-generation.json").write_text(json.dumps({"version":"0.3.0","real_model":True,"cases":cases},indent=2),encoding="utf-8")
if __name__=="__main__":main()
