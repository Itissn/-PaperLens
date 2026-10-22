from unittest.mock import patch
from paperlens.semantic import default_verifier
from paperlens.answer import answer
def test_real_nli_detects_paraphrase_and_contradiction():
    verifier=default_verifier()
    good=verifier.predict("The experiment used thirty random seeds.","The study ran with thirty random seeds.")
    bad=verifier.predict("The experiment used thirty random seeds.","The study ran with fifty random seeds.")
    assert good["entailment"]>.65 and bad["contradiction"]>.65
def test_semantic_gate_catches_same_number_opposite_claim():
    hit={"citation_id":1,"document_id":"paper","title":"Experiment","page":1,"text":"The experiment did not use 30 random seeds.","rerank_score":2.0}
    paragraph={"text":"The experiment used 30 random seeds.","items":[],"citation_ids":[1],"support_quotes":[{"citation_id":1,"quote":hit["text"]}]}
    with patch("paperlens.local_llm.generate",return_value=([paragraph],{"input_tokens":10,"output_tokens":10},"fixture")):
        result=answer("How many seeds?",[hit],"local_llm")
    assert result["status"]=="abstained"
    assert result["validation"]["passed"]
    assert result["evidence_assessment"]["reason"]=="semantic_support_failed"
