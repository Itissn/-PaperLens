import json
import numpy as np
import pytest
from paperlens.agent import PaperAgent,ToolError
from paperlens.store import Store
from paperlens.ingest import ingest_bytes,embed_pending
from test_api import make_pdf,FakeEmbedder

class Ranker:
    name="fixture"
    def score(self,q,texts):return [2.0]*len(texts)
class Planner:
    def __init__(self,actions):self.actions=iter(actions);self.messages=[]
    def __call__(self,messages,tools):
        self.messages.append(messages.copy())
        return next(self.actions)
def tool(name,args,id="call1"):
    return {"tool_calls":[{"id":id,"type":"function","function":{"name":name,"arguments":json.dumps(args)}}]}

def test_model_selects_tool_receives_result_then_finishes(tmp_path):
    store=Store(tmp_path);doc=ingest_bytes(store,make_pdf(),"A paper");embed_pending(store,FakeEmbedder())
    plan=Planner([tool("search_papers",{"query":"curriculum learning","k":2}),tool("read_page",{"document_id":doc["id"],"page":1},id="call2"),{"content":"Enough evidence."}])
    agent=PaperAgent(store,FakeEmbedder(),Ranker(),planner=plan)
    result=agent.run("What is curriculum learning?",generator="extractive")
    assert result["status"]=="evidence"
    assert result["agent"]["tool_calls"]==2
    assert result["agent"]["all_cited_pages_read"]
    assert result["agent"]["verification_reads"][0]["page"]==2
    assert result["agent"]["verification_reads"][0]["actor"]=="controller"
    assert any(h["page"]==2 for h in result["citations"])
    assert result["agent"]["read_pages"]==[{"document_id":doc["id"],"page":1},{"document_id":doc["id"],"page":2}]
    assert result["agent"]["trace"][0]["tool"]=="search_papers"
    assert result["agent"]["trace"][0]["outcome"]=="ok"
    assert any(m["role"]=="tool" for m in plan.messages[1])
    all_pages=Planner([tool("search_papers",{"query":"curriculum learning","k":2}),tool("read_page",{"document_id":doc["id"],"page":1}),tool("read_page",{"document_id":doc["id"],"page":2}),tool("finish_research",{})])
    complete=PaperAgent(store,FakeEmbedder(),Ranker(),planner=all_pages).run("What is curriculum learning?",generator="extractive")
    assert complete["agent"]["all_cited_pages_read"]


def test_unlisted_tools_and_unknown_arguments_are_rejected(tmp_path):
    agent=PaperAgent(Store(tmp_path),FakeEmbedder(),Ranker())
    with pytest.raises(ToolError):agent.execute("shell",{"command":"echo fake"})
    with pytest.raises(ToolError):agent.execute("list_papers",{"path":"../../private"})
    with pytest.raises(ToolError):agent.execute("read_page",{"document_id":"../../private","page":1})
    with pytest.raises(ToolError):agent.execute("search_papers",{"query":"test","k":100})

def test_invalid_page_and_loop_budget_are_explicit(tmp_path):
    agent=PaperAgent(Store(tmp_path),FakeEmbedder(),Ranker())
    with pytest.raises(ToolError):agent.execute("read_page",{"document_id":"0"*20,"page":2})
    planner=Planner([tool("list_papers",{},id=str(i)) for i in range(8)])
    result=PaperAgent(Store(tmp_path),FakeEmbedder(),Ranker(),planner=planner,max_rounds=3).run("Inspect the papers.",generator="extractive")
    assert result["status"]=="abstained"
    assert result["agent"]["stop_reason"]=="round_limit"
    assert result["agent"]["tool_calls"]==3

def test_read_page_tracks_real_source_and_bounds_output(tmp_path):
    store=Store(tmp_path);doc=ingest_bytes(store,make_pdf(),"A paper")
    agent=PaperAgent(store,FakeEmbedder(),Ranker())
    result,hits=agent.execute("read_page",{"document_id":doc["id"],"page":1})
    assert result["page"]==1
    assert len(result["text"])<=4000
    assert hits[0]["page"]==1 and hits[0]["context_chunk_ids"]


def test_native_planner_uses_supported_tool_choice(monkeypatch):
    from paperlens import agent as module
    captured={}
    def request(payload):
        captured.update(payload)
        return {"choices":[{"message":tool("read_page",{"document_id":"a"*20,"page":1})}],"usage":{"prompt_tokens":5,"completion_tokens":2}}
    monkeypatch.setattr(module,"local_request",request)
    message=module.native_plan([], [t for t in module.TOOLS if t["function"]["name"]=="read_page"])
    assert captured["tool_choice"]=="required"
    assert len(captured["tools"])==1
    assert message["_usage"]["completion_tokens"]==2
