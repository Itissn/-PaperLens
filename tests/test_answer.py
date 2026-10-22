import pytest
from paperlens.answer import answer,validate_generated,GenerationError

HITS=[{"citation_id":1,"text":"Curriculum learning orders training instances by difficulty. The strategy helps solve routing problems.","semantic_score":0.7,"title":"Paper","page":2}]

def test_extract_is_exact_and_cited():
    result=answer("How does curriculum learning order training instances?",HITS)
    assert result["status"]=="evidence"
    assert result["paragraphs"][0]["text"] in HITS[0]["text"]
    assert result["paragraphs"][0]["citation_ids"]==[1]
    assert result["usage"]["output_tokens"]==0

def test_abstain_with_no_evidence():
    assert answer("tax",[])["status"]=="abstained"

def test_invented_citation_and_missing_structure_rejected():
    for payload in ({},{"paragraphs":[{"text":"Fake claim","citation_ids":[99]}]},{"paragraphs":[{"text":"No citation","citation_ids":[]}]}):
        with pytest.raises(GenerationError): validate_generated(payload,HITS)

def test_valid_citation_only_checks_structure_not_truth():
    assert validate_generated({"paragraphs":[{"text":"A claim to check","citation_ids":[1]}]},HITS)
