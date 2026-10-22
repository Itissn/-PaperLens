import numpy as np
import pytest
from paperlens.retrieval import bm25_scores, cosine_scores, reciprocal_rank_fusion

def test_bm25_ranks_topic_and_ignores_stop_words():
    scores=bm25_scores("What is curriculum learning?",["Learning with curriculum progression","A bank transaction ledger"])
    assert scores[0]>scores[1]==0
    assert len(bm25_scores("anything",[]))==0

def test_cosine_real_math_zero_safe():
    scores=cosine_scores([1,0],[[1,0],[0,1],[0,0]])
    assert np.allclose(scores,[1,0,0])

def test_rrf_rewards_agreement_and_uses_rank_not_raw_score():
    result=reciprocal_rank_fusion([[0,1],[1,2]])
    assert result[1]>result[0]>result[2]
