"""Evidence selection, source-exact extract baseline and guarded local generation."""
import json
import math
import os
import re
import urllib.request
from .retrieval import tokens
from .reranking import RELEVANCE_CUTOFF

class GenerationError(Exception): pass

def validate_generated(payload,hits):
    """Legacy citation shape check, retained for baseline comparisons."""
    valid={h["citation_id"] for h in hits}
    if not isinstance(payload,dict) or not isinstance(payload.get("paragraphs"),list):
        raise GenerationError("LLM did not return the required JSON structure.")
    paragraphs=payload["paragraphs"]
    if not 1<=len(paragraphs)<=5:raise GenerationError("Invalid number of paragraphs.")
    clean=[]
    for p in paragraphs:
        if not isinstance(p,dict):raise GenerationError("Invalid paragraph.")
        text=p.get("text");cites=p.get("citation_ids")
        if not isinstance(text,str) or not 1<=len(text)<=1800:raise GenerationError("Invalid paragraph text.")
        if not isinstance(cites,list) or not cites or any(type(c) is not int or c not in valid for c in cites):
            raise GenerationError("LLM used a missing or invented citation.")
        clean.append({"text":text,"citation_ids":sorted(set(cites))})
    return clean

def assess_evidence(query,hits):
    if not hits:
        return [],{"sufficient":False,"reason":"empty_retrieval","method":"none","retained":0}
    if any("rerank_score" in h for h in hits):
        if any(not isinstance(h.get("rerank_score"),(int,float)) or not math.isfinite(h["rerank_score"]) for h in hits):
            raise GenerationError("Evidence contains incomplete or invalid reranker scores.")
        positive_docs={h["document_id"] for h in hits if h["rerank_score"]>=RELEVANCE_CUTOFF and "document_id" in h}
        chosen=[h for h in hits if h["rerank_score"]>=RELEVANCE_CUTOFF or (h.get("context_expansion") and h["document_id"] in positive_docs)]
        return chosen,{"sufficient":bool(chosen),"reason":"above_reranker_cutoff" if chosen else "below_reranker_cutoff",
            "method":"cross_encoder_logit_policy","cutoff":RELEVANCE_CUTOFF,
            "top_score":max(h["rerank_score"] for h in hits),"retained":len(chosen),
            "limitation":"Relevance cutoff is a development heuristic, not a calibrated probability or proof of answerability."}
    meaningful=set(tokens(query))
    overlap=max(len(meaningful & set(tokens(h["text"]))) for h in hits)
    cosine=max(h.get("semantic_score") or 0 for h in hits)
    enough=overlap>0 or cosine>=0.50
    return hits if enough else [],{"sufficient":enough,"reason":"legacy_overlap_heuristic","method":"v0.1_baseline","retained":len(hits) if enough else 0}

def ollama_generate(query,hits,ranker=None,emit=None):
    from .grounding import prepare_context,output_schema,decode_grounded
    from .local_llm import SYSTEM_PROMPT
    model=os.environ.get("PAPERLENS_OLLAMA_MODEL")
    if not model:raise GenerationError("Set PAPERLENS_OLLAMA_MODEL and start Ollama first.")
    context,sources=prepare_context(query,hits,ranker)
    if not sources:raise GenerationError("No bounded source context available.")
    endpoint=os.environ.get("PAPERLENS_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")+"/api/chat"
    body={"model":model,"stream":bool(emit),"keep_alive":0,"format":output_schema(sources),"options":{"temperature":0,"num_predict":700,"num_thread":6,"seed":42},
          "messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps({"excerpts":context,"question":query},ensure_ascii=False)}]}
    request=urllib.request.Request(endpoint,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=120) as response:
            if emit:
                from .events import draft_text
                emit("generation_start",{"model":model,"pending_validation":True})
                pieces=[];size=0;final=None
                while True:
                    line=response.readline(100001)
                    if not line:break
                    size+=len(line)
                    if len(line)>100000 or size>500000:raise GenerationError("Ollama stream exceeded its limit.")
                    event=json.loads(line);piece=event.get("message",{}).get("content") or ""
                    if piece:
                        pieces.append(piece);emit("draft",{"text":draft_text("".join(pieces)),"verified":False})
                    if event.get("done"):final=event;break
                if final is None:raise GenerationError("Ollama stream ended before completion.")
                data={**final,"message":{"content":"".join(pieces)}}
                raw=json.dumps(data).encode()
            else:raw=response.read(200_001)
        if len(raw)>200_000:raise GenerationError("LLM response too large.")
        data=json.loads(raw)
        if data.get("done_reason")=="length":raise GenerationError("LLM output truncated.")
        paragraphs=decode_grounded(json.loads(data["message"]["content"]),sources)
        return paragraphs,{"input_tokens":data.get("prompt_eval_count"),"output_tokens":data.get("eval_count")},model
    except GenerationError:raise
    except Exception as exc:
        raise GenerationError("Ollama unavailable, timed out, or returned invalid structured output.") from exc

def answer(query,hits,generator="extractive",ranker=None,emit=None):
    from .grounding import check_support
    if generator not in ("extractive","local_llm","ollama"):raise ValueError("Unknown generator.")
    selected,assessment=assess_evidence(query,hits)
    base={"generator":generator,"model":None,"usage":{"input_tokens":0,"output_tokens":0},
          "api_cost_usd":0,"evidence_assessment":assessment,"generation_context_ids":[]}
    if not selected:
        return {**base,"status":"abstained","paragraphs":[],"citations":[],
                "notice":"No sufficiently relevant source evidence was found, so no answer was generated. Reranker scores and the cutoff are screening heuristics, not proof of correctness."}
    if generator=="extractive":
        meaningful=set(tokens(query));paragraphs=[]
        for h in selected[:3]:
            sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])",h["text"]) if len(s.strip())>=35] or [h["text"]]
            sentence=max(sentences,key=lambda s:(len(meaningful & set(tokens(s))),-len(s)))
            paragraphs.append({"text":sentence,"citation_ids":[h["citation_id"]],
                "support_quotes":[{"citation_id":h["citation_id"],"quote":sentence}]})
        notice="Extractive answer: passages selected directly from the papers without a language-model call. Check whether they fully answer the question."
        status="evidence";validation={"passed":True,"errors":[],"scope":"Exact source extraction; relevance is not guaranteed."}
    else:
        context=selected[:12]
        if generator=="local_llm":
            from .local_llm import generate
            paragraphs,usage,model=generate(query,context,ranker=ranker,emit=emit)
            from .completeness import check as check_complete
            completeness=check_complete(query,paragraphs)
            if paragraphs and not completeness["passed"]:
                if emit:emit("repair",{"message":"The answer omitted requested items. Retrying from source evidence."})
                old_usage=usage
                paragraphs,usage,model=generate(query,context,ranker=ranker,emit=emit,feedback="Name exactly "+str(completeness["requested_items"])+" distinct items. Include their names in both text and items. If the evidence is insufficient, decline.")
                usage={k:(usage[k]+old_usage[k] if usage[k] is not None and old_usage[k] is not None else None) for k in usage}
        else:paragraphs,usage,model=ollama_generate(query,context,ranker=ranker,emit=emit)
        base.update(usage=usage,model=model,generation_context_ids=[h["citation_id"] for h in context])
        if not paragraphs:
            return {**base,"status":"abstained","paragraphs":[],"citations":[],
                    "notice":"The model found the available passages insufficient to answer this question. Retrieved evidence is retained for review.",
                    "evidence_assessment":{**assessment,"reason":"model_declined"}}
        validation=check_support(paragraphs,context)
        if not validation["passed"]:
            return {**base,"status":"abstained","paragraphs":[],"citations":[],"validation":validation,
                    "evidence_assessment":{**assessment,"reason":"support_check_failed"},
                    "notice":"The generated answer failed source-quote or numeric-coverage checks and was withheld. Review the evidence or switch to extractive mode."}
        from .completeness import check as check_complete
        completeness=check_complete(query,paragraphs)
        base["completeness"]=completeness
        if emit:emit("validation",{"message":"Checking semantic support and answer completeness."})
        try:
            from .semantic import default_verifier
            semantic=default_verifier().check(paragraphs)
        except Exception:
            semantic={"passed":False,"reason":"semantic_model_unavailable","scope":"No semantic verdict was produced."}
        base["semantic_check"]=semantic
        if not completeness["passed"] or not semantic["passed"]:
            return {**base,"status":"abstained","paragraphs":[],"citations":[],"validation":validation,"review":{"verified":False,"draft":paragraphs},
                    "evidence_assessment":{**assessment,"reason":"incomplete_answer" if not completeness["passed"] else "semantic_support_failed"},
                    "notice":"The draft failed answer-completeness or semantic-support screening and was withheld. Review the retrieved evidence."}
        notice="Local model answer with supporting source excerpts below. Source identity and numeric coverage were checked; semantic support and answer completeness still need human review."
        status="generated"
    cited={c for p in paragraphs for c in p["citation_ids"]}
    return {**base,"status":status,"paragraphs":paragraphs,"citations":[h for h in selected if h["citation_id"] in cited],
            "notice":notice,"validation":validation}
