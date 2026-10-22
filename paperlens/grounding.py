"""Resolve source IDs to exact text and apply limited, explicit support checks.
These checks do not establish entailment or full answer correctness.
"""
from decimal import Decimal
import re

def _error(message):
    from .answer import GenerationError
    return GenerationError(message)

def make_context(hits,max_chars=6000,max_passages=4):
    contexts=[];sources={};seen=set();used=0
    for h in hits[:max_passages]:
        sentences=[]
        for sentence in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9])",h["text"]):
            sentence=sentence.strip()
            if len(sentence)<20:continue
            offset=0
            while offset<len(sentence):
                end=min(len(sentence),offset+480)
                if end<len(sentence):
                    boundary=sentence.rfind(" ",offset,end)
                    if boundary>offset:end=boundary
                quote=sentence[offset:end].strip()
                offset=end
                while offset<len(sentence) and sentence[offset].isspace():offset+=1
                if len(quote)<15:continue
                identity=(h.get("document_id"),h.get("page"),quote)
                if identity in seen or used+len(quote)>max_chars:continue
                sid="S"+str(len(sources)+1)
                sources[sid]={"citation_id":h["citation_id"],"quote":quote}
                sentences.append({"sentence_id":sid,"text":quote})
                used+=len(quote);seen.add(identity)
        if sentences:contexts.append({"citation_id":h["citation_id"],"title":h["title"],"page":h["page"],"sentences":sentences})
    return contexts,sources

def prepare_context(query,hits,ranker=None):
    if ranker is None:return make_context(hits)
    _,candidates=make_context(hits,max_chars=16000,max_passages=8)
    if not candidates:return [],{}
    ids=list(candidates)
    scores=ranker.score(query,[candidates[s]["quote"] for s in ids])
    from .completeness import requested_count
    count=requested_count(query)
    chosen=sorted(range(len(ids)),key=lambda i:(-scores[i],i))[:(16 if count else 8)]
    source_hits={h["citation_id"]:h for h in hits}
    contexts=[];sources={};grouped={}
    for i in chosen:
        support=candidates[ids[i]]
        citation=support["citation_id"]
        h=source_hits[citation]
        sid="S"+str(len(sources)+1)
        sources[sid]=support
        if citation not in grouped:
            grouped[citation]={"citation_id":citation,"title":h["title"],"page":h["page"],"sentences":[]}
            contexts.append(grouped[citation])
        grouped[citation]["sentences"].append({"sentence_id":sid,"text":support["quote"]})
    return contexts,sources

def output_schema(sources):
    return {"type":"object","properties":{
       "answerable":{"type":"boolean"},
       "paragraphs":{"type":"array","maxItems":2,"items":{
          "type":"object","properties":{
              "text":{"type":"string"},
              "items":{"type":"array","maxItems":12,"items":{"type":"string"}},"support_sentence_ids":{"type":"array","minItems":1,"maxItems":3,
                                      "items":{"type":"string","enum":list(sources)}}},
          "required":["text","support_sentence_ids","items"],"additionalProperties":False}}},
       "required":["answerable","paragraphs"],"additionalProperties":False}

def decode_grounded(payload,sources):
    if not isinstance(payload,dict) or type(payload.get("answerable")) is not bool:
        raise _error("Model did not return an explicit answerability decision.")
    paragraphs=payload.get("paragraphs")
    if not isinstance(paragraphs,list):raise _error("Model paragraphs must be a list.")
    if not payload["answerable"]:
        if paragraphs:raise _error("A declined answer must not contain claims.")
        return []
    if not 1<=len(paragraphs)<=2:raise _error("Model answer must contain 1–2 paragraphs.")
    clean=[]
    for item in paragraphs:
        if not isinstance(item,dict):raise _error("Invalid model paragraph.")
        text=item.get("text");ids=item.get("support_sentence_ids")
        if not isinstance(text,str) or not text.strip() or len(text)>1800:
            raise _error("Invalid model answer text.")
        if not isinstance(ids,list) or not 1<=len(ids)<=3 or any(not isinstance(s,str) or s not in sources for s in ids):
            raise _error("Model referenced an unknown supporting sentence.")
        quotes=[dict(sources[s]) for s in dict.fromkeys(ids)]
        items=item.get("items",[])
        if not isinstance(items,list) or any(not isinstance(x,str) for x in items):raise _error("Invalid enumeration items.")
        clean.append({"text":text.strip(),"items":items,"citation_ids":sorted({q["citation_id"] for q in quotes}),"support_quotes":quotes})
    return clean

def _numbers(text):
    # Conservative numeric guard, not mathematical equivalence or entailment.
    values=set()
    for match in re.findall(r"(?<![A-Za-z])\d+(?:,\d{3})*(?:\.\d+)?%?",text):
        percent=match.endswith("%")
        value=Decimal(match.rstrip("%").replace(",",""))
        values.add(value/100 if percent else value)
    return values

def check_support(paragraphs,hits):
    lookup={h["citation_id"]:h for h in hits}
    errors=[]
    for i,p in enumerate(paragraphs):
        quotes=p.get("support_quotes",[])
        if not quotes:
            errors.append({"paragraph":i,"code":"missing_support_quote"});continue
        good=[]
        for q in quotes:
            h=lookup.get(q.get("citation_id"))
            quote=q.get("quote")
            if h is None or not isinstance(quote,str) or not quote.strip() or quote not in h["text"] or q["citation_id"] not in p["citation_ids"]:
                errors.append({"paragraph":i,"code":"quote_source_mismatch"})
            else:good.append(quote)
        missing=_numbers(p["text"])-_numbers(" ".join(good))
        if missing:
            errors.append({"paragraph":i,"code":"unsupported_number","values":sorted(str(n) for n in missing)})
    return {"passed":not errors,"errors":errors,"scope":"Exact quoted-source identity and numeric coverage only; semantic support and answer completeness still require human review."}
