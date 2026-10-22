"""Generic definition-context expansion for explicitly numbered list questions."""
import re
from .completeness import requested_count
from .context import page_window
from .retrieval import tokens
def expand_definitions(store,query,hits,ranker):
    if not hits or requested_count(query) is None:return hits
    doc=hits[0]["document_id"];rows=store.chunks(doc)
    terms={t.rstrip("s") for t in tokens(query)}
    candidates=[]
    for i,row in enumerate(rows):
        text=row["text"]
        definition=bool(re.search(r"\b(defin\w*|representation|consist\w*|compris\w*|descriptor is|corresponding)\b",text,re.I))
        if not definition:continue
        overlap=len(terms & {t.rstrip("s") for t in tokens(text)})
        if overlap:candidates.append((overlap+3*definition,i))
    chosen=[i for _,i in sorted(candidates,reverse=True)[:4]]
    additional=[]
    for i in chosen:
        row=rows[i];text,ids=page_window(rows,i,max_words=360)
        additional.append({k:v for k,v in row.items() if k not in ("vector","model")})
        additional[-1].update(text=text,context_chunk_ids=ids,context_expansion=True,pdf_url=f"/api/documents/{doc}/pdf#page={row['page']}")
    if additional:
        scores=ranker.score(query,[h["text"] for h in additional])
        for h,s in zip(additional,scores):h["rerank_score"]=float(s)
    combined=[];seen=set()
    for h in additional+hits:
        key=(h["document_id"],h["page"],h["text"])
        if key not in seen:combined.append(dict(h));seen.add(key)
    for i,h in enumerate(combined,1):h["citation_id"]=i
    return combined[:12]
