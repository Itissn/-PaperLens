"""Local learned entailment check; a fallible screening model, not a truth oracle."""
import json,re,threading
from pathlib import Path
import numpy as np
MODEL="Xenova/nli-deberta-v3-xsmall"
class SemanticVerifier:
    def __init__(self,folder):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder=Path(folder)
        if not (folder/"provenance.json").exists():raise RuntimeError("Semantic model unavailable. Run scripts/setup_nli.py.")
        self.tokenizer=Tokenizer.from_file(str(folder/"tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512,strategy="only_first")
        self.tokenizer.enable_padding()
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(folder/"model.onnx"),sess_options=options,providers=["CPUExecutionProvider"])
        self.labels=json.loads((folder/"config.json").read_text())["id2label"]
        self.lock=threading.Lock()
    def predict(self,premise,claim):
        with self.lock:
            encoded=self.tokenizer.encode(premise,claim)
            values={"input_ids":np.array([encoded.ids],dtype=np.int64),"attention_mask":np.array([encoded.attention_mask],dtype=np.int64),"token_type_ids":np.array([encoded.type_ids],dtype=np.int64)}
            logits=self.session.run(None,{x.name:values[x.name] for x in self.session.get_inputs()})[0][0]
        scores=np.exp(logits-np.max(logits));scores/=scores.sum()
        return {self.labels[str(i)]:float(value) for i,value in enumerate(scores)}
    def check(self,paragraphs):
        items=[]
        for i,p in enumerate(paragraphs):
            premise=" ".join(q["quote"] for q in p.get("support_quotes",[]))
            claims=[c.strip() for c in re.split(r"(?<=[.!?])\s+(?=[A-Z])",p["text"]) if c.strip()]
            if len(claims)>8:return {"passed":False,"model":MODEL,"reason":"too_many_claims","items":items}
            for claim in claims:
                scores=self.predict(premise,claim)
                items.append({"paragraph":i,"claim":claim,"scores":scores,"passed":scores["entailment"]>=0.65 and scores["contradiction"]<0.15})
        return {"passed":bool(items) and all(x["passed"] for x in items),"model":MODEL,"threshold":0.65,"items":items,"scope":"Learned English NLI screen on quoted evidence. Not a calibrated correctness probability or independent human review."}
_INSTANCE=None
_LOCK=threading.Lock()
def default_verifier():
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:_INSTANCE=SemanticVerifier(Path(__file__).resolve().parents[1]/".cache"/"nli")
    return _INSTANCE
