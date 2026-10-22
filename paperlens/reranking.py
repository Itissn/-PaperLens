"""Local query-passage cross encoder. Scores are logits, never confidence."""
import math
import os
from pathlib import Path

MODEL="Xenova/ms-marco-MiniLM-L-6-v2"
RELEVANCE_CUTOFF=0.0  # Development policy, deliberately exposed and evaluated.

class Reranker:
    name=MODEL
    def __init__(self,cache_dir):
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        cache=Path(cache_dir)
        os.environ.setdefault("HF_HUB_DISABLE_XET","1")
        manual=cache/"verified-model"
        options={"specific_model_path":str(manual)} if (manual/"provenance.json").exists() else {}
        self.model=TextCrossEncoder(self.name,cache_dir=str(cache),threads=4,**options)
    def score(self,query,texts):
        values=[float(x) for x in self.model.rerank(query,texts,batch_size=8)]
        if len(values)!=len(texts) or any(not math.isfinite(x) for x in values):
            raise ValueError("Reranker returned invalid scores.")
        return values
