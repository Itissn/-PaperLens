"""A real pretrained neural encoder, running locally on CPU via ONNX."""
import os
from pathlib import Path
import numpy as np

MODEL = "BAAI/bge-small-en-v1.5"

class Embedder:
    name = MODEL
    def __init__(self, cache_dir):
        # Cache all Hugging Face artifacts on the project disk, not the system disk.
        cache_dir = Path(cache_dir)
        os.environ.setdefault("HF_HOME", str(cache_dir / "hf"))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name=self.name, cache_dir=str(cache_dir), threads=4)
    def documents(self, texts):
        return np.asarray(list(self.model.passage_embed(texts, batch_size=16)), dtype=np.float32)
    def query(self, text):
        return np.asarray(list(self.model.query_embed(text))[0], dtype=np.float32)
