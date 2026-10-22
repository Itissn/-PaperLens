"""Reproducible retrieval evaluation. No LLM or paid API calls."""
import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path
from paperlens.store import Store
from paperlens.embeddings import Embedder
from paperlens.retrieval import Retriever
from paperlens.answer import answer
from paperlens.reranking import Reranker,RELEVANCE_CUTOFF

ROOT=Path(__file__).resolve().parent

def normalise(text): return " ".join(text.lower().split())

def matches(hit,label,id_to_arxiv):
    return (id_to_arxiv.get(hit["document_id"])==label["arxiv_id"]
            and hit["page"]==label["page"]
            and any(normalise(p) in normalise(hit["text"]) for p in label["contains_any"]))

def score_hits(hits,relevant,id_to_arxiv):
    ranks=[i for i,h in enumerate(hits,1) if any(matches(h,l,id_to_arxiv) for l in relevant)]
    # Multiple chunks on the same annotated page count once, not repeatedly.
    pages={(l["arxiv_id"],l["page"]) for l in relevant}
    found={(l["arxiv_id"],l["page"]) for l in relevant if any(matches(h,l,id_to_arxiv) for h in hits)}
    return {"hit":bool(ranks),"first_relevant_rank":min(ranks) if ranks else None,
            "reciprocal_rank":1/min(ranks) if ranks else 0,
            "page_recall":len(found)/len(pages) if pages else None}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-dir",type=Path,default=ROOT/"data")
    parser.add_argument("--labels",type=Path,default=ROOT/"eval_cases.json")
    parser.add_argument("--report",type=Path,default=ROOT/"reports"/"retrieval-evaluation.json")
    args=parser.parse_args()
    label_path=args.labels
    labels=json.loads(label_path.read_text(encoding="utf-8"))
    store=Store(args.data_dir)
    # Ignore later personal uploads: this benchmark has a fixed corpus.
    documents=[d for d in store.documents() if d["source_url"].startswith("https://arxiv.org/abs/")]
    lookup={d["id"]:d["source_url"].split("/")[-1] for d in documents}
    start=time.perf_counter()
    embedder=Embedder(ROOT/".cache"/"embeddings")
    model_load=(time.perf_counter()-start)*1000
    # Fixed, pre-registered corpus: store wrapper filters non-benchmark docs.
    class FixedCorpus:
        def chunks(self,document_id=None):
            return [r for r in store.chunks(document_id) if r["document_id"] in lookup]
    reranker=Reranker(ROOT/".cache"/"reranker")
    retriever=Retriever(FixedCorpus(),embedder,reranker)
    variants=[("lexical","lexical",False),("semantic","semantic",False),("hybrid","hybrid",False),("hybrid_rerank","hybrid",True)]
    retriever.search("warm up query",mode="semantic",k=5)
    results=[]
    k=5
    for c in labels["cases"]:
        per_mode={}
        for name,mode,use_rerank in variants:
            result=retriever.search(c["question"],mode,k,rerank=use_rerank)
            hits=result["hits"]
            baseline=answer(c["question"],hits)
            scored=score_hits(hits,c["relevant"],lookup) if c["answerable"] else {}
            # This checks exact quotation, NOT semantic answer correctness.
            exact=all(p["text"] in next(h["text"] for h in hits if h["citation_id"]==p["citation_ids"][0])
                      for p in baseline["paragraphs"])
            per_mode[name]={**scored,"latency_ms":result["latency_ms"],"abstained":baseline["status"]=="abstained",
                "exact_quote_integrity":exact,"evidence_assessment":baseline["evidence_assessment"],
                "hits":[{"arxiv_id":lookup[h["document_id"]],"page":h["page"],"chunk_id":h["id"],"text":h["text"],"rerank_score":h.get("rerank_score")} for h in hits]}
        results.append({**c,"results":per_mode})
    summary={}
    for mode,_,_ in variants:
        positive=[c["results"][mode] for c in results if c["answerable"]]
        negative=[c["results"][mode] for c in results if not c["answerable"]]
        summary[mode]={"positive_evidence_rate":statistics.mean(not r["abstained"] for r in positive),"hit_rate":statistics.mean(r["hit"] for r in positive),
             "page_recall":statistics.mean(r["page_recall"] for r in positive),
             "mrr":statistics.mean(r["reciprocal_rank"] for r in positive),
             "median_latency_ms":statistics.median(c["results"][mode]["latency_ms"] for c in results),
             "unanswerable_abstention_rate":statistics.mean(r["abstained"] for r in negative),
             "exact_quote_integrity":all(c["results"][mode]["exact_quote_integrity"] for c in results)}
    report={"created_date":labels["created_date"],"project_version":"0.3.0","reranker":reranker.name,"reranker_cutoff":RELEVANCE_CUTOFF,"k":k,"answerable_cases":sum(c["answerable"] for c in results),
       "unanswerable_cases":sum(not c["answerable"] for c in results),"label_policy":labels["label_policy"],
       "limitations":"Small manually constructed development set; relevance labels are not exhaustive. No held-out or human-rated LLM answer accuracy measured. Timings are one local warm run; retrieval includes query embedding but excludes model loading. Quote integrity only checks exact excerpts. Answerability policies are heuristics. Positive evidence coverage is reported alongside negative refusals; exact quotes do not establish answer correctness.",
       "environment":{"python":platform.python_version(),"platform":platform.platform(),"model":embedder.name,
                      "model_load_ms":round(model_load,2),"index_config":json.loads((store.folder/"index-config.json").read_text()) if (store.folder/"index-config.json").exists() else {"chunk_words":120,"overlap_words":25},"corpus_sha256":{d["source_url"]:d["sha256"] for d in documents},
                      "labels_sha256":hashlib.sha256(label_path.read_bytes()).hexdigest()},
       "summary":summary,"cases":results}
    out=ROOT/"reports";out.mkdir(exist_ok=True)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("Report:",args.report)
if __name__=="__main__":main()
