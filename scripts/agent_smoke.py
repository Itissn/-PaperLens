"""Exercise native Qwen-selected tool calls. No fixture planner in this script."""
import json
from pathlib import Path
from paperlens.store import Store
from paperlens.embeddings import Embedder
from paperlens.reranking import Reranker
from paperlens.agent import PaperAgent
ROOT=Path(__file__).resolve().parents[1]
def main():
    agent=PaperAgent(Store(ROOT/"data"),Embedder(ROOT/".cache"/"embeddings"),Reranker(ROOT/".cache"/"reranker"))
    question="How many random seeds were used in the BN-GPGLS experiments? Search the papers and inspect the relevant page."
    result=agent.run(question,generator="local_llm")
    assert result["agent"]["tool_calls"]>0
    assert result["agent"]["page_verification"]
    assert any(s["tool"]=="search_papers" and s["outcome"]=="ok" for s in result["agent"]["trace"])
    assert any(s["tool"]=="read_page" and s["outcome"]=="ok" for s in result["agent"]["trace"])
    report={"version":"0.2.0","question":question,"result":result,"verification":"Native model tool calls executed; final answer correctness is reviewed separately."}
    (ROOT/"reports"/"agent-smoke.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"status":result["status"],"tools":[{"name":t["tool"],"args":t["arguments"],"outcome":t["outcome"]} for t in result["agent"]["trace"]],"paragraphs":result["paragraphs"],"stop_reason":result["agent"]["stop_reason"]},ensure_ascii=True,indent=2),flush=True)
if __name__=="__main__":main()
