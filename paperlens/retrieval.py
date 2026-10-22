"""Three comparable strategies. RRF merges ranks, not incomparable raw scores."""
from collections import Counter
import math
import re
import time
import numpy as np
from .context import page_window

STOP = set("a an the is are was were be been being of for to in on at and or with by from as it its this that these those what which how why when where do does did can could would should about paper papers study studies method methods use used using".split())

def tokens(text):
    return [x for x in re.findall(r"[a-z0-9]+", text.lower()) if x not in STOP and len(x)>1]

def bm25_scores(query, texts):
    bags=[Counter(tokens(t)) for t in texts]
    if not bags: return np.zeros(0)
    avg=sum(sum(b.values()) for b in bags)/len(bags) or 1
    scores=np.zeros(len(bags))
    for term in set(tokens(query)):
        df=sum(term in b for b in bags)
        idf=math.log(1+(len(bags)-df+0.5)/(df+0.5))
        for i,b in enumerate(bags):
            tf=b[term]
            scores[i]+=idf*tf*2.5/(tf+1.5*(0.25+0.75*sum(b.values())/avg))
    return scores

def cosine_scores(query_vector, vectors):
    q=np.asarray(query_vector,dtype=np.float32)
    matrix=np.asarray(vectors,dtype=np.float32)
    norms=np.linalg.norm(matrix,axis=1)*np.linalg.norm(q)
    return (matrix@q)/np.maximum(norms,1e-12)

def reciprocal_rank_fusion(rankings, constant=60):
    fused=Counter()
    for ranking in rankings:
        for rank, index in enumerate(ranking,1):
            fused[index]+=1/(constant+rank)
    return fused

class Retriever:
    def __init__(self, store, embedder, reranker=None):
        self.store=store; self.embedder=embedder; self.reranker=reranker
    def search(self, query, mode="hybrid", k=5, document_id=None, rerank=False):
        if mode not in ("lexical","semantic","hybrid"): raise ValueError("Unknown search mode.")
        if not query.strip() or not 1 <= k <= 10: raise ValueError("Query/k invalid.")
        if rerank and self.reranker is None: raise ValueError("Reranker is not configured.")
        start=time.perf_counter()
        rows=self.store.chunks(document_id)
        if not rows: return {"hits":[],"latency_ms":0,"mode":mode,"rerank":{"enabled":bool(rerank),"candidate_count":0,"model":self.reranker.name if rerank else None}}
        lexical=bm25_scores(query,[r["text"] for r in rows])
        semantic=np.zeros(len(rows))
        if mode!="lexical":
            if any(r["model"]!=self.embedder.name or r["vector"] is None for r in rows):
                raise ValueError("Index incomplete. Run: python manage.py index")
            vectors=[np.frombuffer(r["vector"],dtype="<f4") for r in rows]
            semantic=cosine_scores(self.embedder.query(query),vectors)
        lexical_rank=sorted((i for i,s in enumerate(lexical) if s>0),key=lambda i:(-lexical[i],rows[i]["id"]))
        semantic_rank=sorted(range(len(rows)),key=lambda i:(-semantic[i],rows[i]["id"]))
        if mode=="hybrid":
            fused=reciprocal_rank_fusion([lexical_rank[:40],semantic_rank[:40]])
            rank=sorted(fused,key=lambda i:(-fused[i],rows[i]["id"]))
            scores=fused
        elif mode=="lexical": rank=lexical_rank; scores=lexical
        else: rank=semantic_rank; scores=semantic
        rerank_scores={}
        expanded={}
        candidate_count=0
        if rerank:
            candidates=rank[:30]
            candidate_count=len(candidates)
            if candidates:
                expanded={i:page_window(rows,i) for i in candidates}
                values=self.reranker.score(query,[expanded[i][0] for i in candidates])
                if len(values)!=len(candidates) or any(not math.isfinite(float(v)) for v in values):
                    raise ValueError("Invalid reranker scores.")
                rerank_scores=dict(zip(candidates,values))
                rank=sorted(candidates,key=lambda i:(-rerank_scores[i],rows[i]["id"]))
                seen=set()
                unique=[]
                for i in rank:
                    identity=(rows[i]["document_id"],rows[i]["page"],expanded[i][0])
                    if identity not in seen:unique.append(i);seen.add(identity)
                rank=unique
        hits=[]
        for i in rank[:k]:
            row={a:b for a,b in rows[i].items() if a not in ("vector","model")}
            row.update(score=round(float(scores[i]),6),lexical_score=round(float(lexical[i]),4),
                       semantic_score=round(float(semantic[i]),4) if mode!="lexical" else None,
                       citation_id=len(hits)+1)
            if rerank:
                row["rerank_score"]=round(float(rerank_scores[i]),5)
                row["text"],row["context_chunk_ids"]=expanded[i]
            row["pdf_url"]=f"/api/documents/{row['document_id']}/pdf#page={row['page']}"
            hits.append(row)
        return {"hits":hits,"latency_ms":round((time.perf_counter()-start)*1000,2),"mode":mode,"rerank":{"enabled":bool(rerank),"candidate_count":candidate_count,"model":self.reranker.name if rerank else None}}
