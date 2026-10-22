import numpy as np
import pytest
from paperlens.retrieval import Retriever
class Store:
    def chunks(self,document_id=None):
        return [{"id":str(i),"document_id":"d","title":"Paper","page":i+1,"position":0,"source_url":"","status":"paper","text":"routing details "+str(i),"vector":np.array([1,0],dtype="<f4").tobytes(),"model":"fake"} for i in range(45)]
class Encoder:
    name="fake"
    def query(self,q):return np.array([1,0],dtype=np.float32)
class Reranker:
    name="fake-reranker"
    def score(self,query,texts):return list(range(len(texts)))
def test_rerank_candidate_budget_and_source_ids():
    result=Retriever(Store(),Encoder(),Reranker()).search("routing",k=5,rerank=True)
    assert result["rerank"]["candidate_count"]==30
    assert len(result["hits"])==5
    assert result["hits"][0]["rerank_score"]==29
    assert [h["citation_id"] for h in result["hits"]]==list(range(1,6))
    assert all("#page=" in h["pdf_url"] for h in result["hits"])
def test_unavailable_reranker_never_silently_claims_reranking():
    with pytest.raises(ValueError,match="Reranker"):
        Retriever(Store(),Encoder()).search("routing",rerank=True)
def test_invalid_model_scores_fail_clearly():
    class Bad:
        name="bad"
        def score(self,q,texts):return [float("nan")]*len(texts)
    with pytest.raises(ValueError,match="scores"):
        Retriever(Store(),Encoder(),Bad()).search("routing",rerank=True)


def test_page_window_stitches_overlap_but_never_other_pages():
    from paperlens.context import page_window
    rows=[
        {"id":"a","document_id":"d","page":1,"position":0,"text":"A B C D"},
        {"id":"b","document_id":"d","page":1,"position":1,"text":"C D E F"},
        {"id":"c","document_id":"d","page":2,"position":0,"text":"SECRET OTHER PAGE"}]
    text,ids=page_window(rows,1)
    assert text=="A B C D E F"
    assert ids==["a","b"]
    assert "SECRET" not in text
