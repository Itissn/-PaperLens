import pytest
from paperlens.grounding import make_context,decode_grounded,check_support
from paperlens.answer import answer,GenerationError

def hit(text,score=2.0,citation=1):
    return {"citation_id":citation,"title":"Paper","page":8,"document_id":"d","text":text,"rerank_score":score,"semantic_score":0.8}

def test_sentence_ids_resolve_to_exact_source_not_model_provided_quotes():
    original=hit("The experiment used 30 matched random seeds. There were 90 monitoring instances.")
    context,sources=make_context([original])
    paragraphs=decode_grounded({"answerable":True,"paragraphs":[{"text":"The experiment used 30 matched random seeds.","support_sentence_ids":["S1"]}]},sources)
    assert paragraphs[0]["citation_ids"]==[1]
    assert paragraphs[0]["support_quotes"][0]["quote"] in original["text"]
    assert check_support(paragraphs,[original])["passed"]

def test_invented_support_sentence_is_rejected():
    _,sources=make_context([hit("A real source passage describing the experiment.")])
    with pytest.raises(GenerationError):
        decode_grounded({"answerable":True,"paragraphs":[{"text":"Fake","support_sentence_ids":["S99"]}]},sources)

def test_wrong_numbers_blocked_even_with_valid_source_reference():
    h=hit("The experiment used 30 matched random seeds.")
    _,sources=make_context([h])
    p=decode_grounded({"answerable":True,"paragraphs":[{"text":"The experiment used 300 matched random seeds.","support_sentence_ids":["S1"]}]},sources)
    result=check_support(p,[h])
    assert not result["passed"]
    assert result["errors"][0]["code"]=="unsupported_number"

def test_quotes_must_belong_to_the_claimed_citation():
    h=hit("The experiment used 30 matched random seeds.")
    p=[{"text":"30 seeds.","citation_ids":[1],"support_quotes":[{"citation_id":1,"quote":"Invented passage with 30 seeds."}]}]
    assert not check_support(p,[h])["passed"]

def test_model_can_decline_without_fake_citations():
    _,sources=make_context([hit("A real source passage describing the experiment.")])
    assert decode_grounded({"answerable":False,"paragraphs":[]},sources)==[]
    with pytest.raises(GenerationError):
        decode_grounded({"answerable":False,"paragraphs":[{"text":"contradiction"}]},sources)

def test_relevance_gate_refuses_before_generator_and_keeps_baseline_explicit():
    result=answer("How many hospital patients?",[hit("A vehicle routing optimisation study.",-5)],generator="local_llm")
    assert result["status"]=="abstained"
    assert result["evidence_assessment"]["reason"]=="below_reranker_cutoff"
    assert result["usage"]["output_tokens"]==0

def test_empty_and_repeated_context_are_bounded():
    assert make_context([])==([], {})
    a=hit("The experiment used 30 matched random seeds.")
    context,sources=make_context([a,a],max_chars=40)
    assert len(sources)<=1


def test_long_paragraph_tail_is_preserved_and_focused():
    from paperlens.grounding import prepare_context
    text=("Long introductory material about a scientific experiment. "*30)+"The final result uses 30 matched seeds."
    h=hit(text)
    _,sources=make_context([h],max_chars=6000)
    assert any("30 matched seeds" in s["quote"] for s in sources.values())
    class Exact:
        def score(self,q,texts):return [100 if "30 matched seeds" in t else -10 for t in texts]
    _,focused=prepare_context("How many seeds?",[h],Exact())
    assert "30 matched seeds" in focused["S1"]["quote"]
    assert all(s["quote"] in text for s in focused.values())
