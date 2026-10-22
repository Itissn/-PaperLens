from evaluate import score_hits

def test_page_recall_deduplicates_chunks_and_requires_topic_anchor():
    lookup={"doc":"x"}
    labels=[{"arxiv_id":"x","page":2,"contains_any":["target evidence"]},{"arxiv_id":"x","page":3,"contains_any":["other evidence"]}]
    hits=[{"document_id":"doc","page":2,"text":"wrong topic"},{"document_id":"doc","page":2,"text":"target evidence"},
          {"document_id":"doc","page":2,"text":"target evidence"}]
    score=score_hits(hits,labels,lookup)
    assert score["first_relevant_rank"]==2
    assert score["reciprocal_rank"]==0.5
    assert score["page_recall"]==0.5
