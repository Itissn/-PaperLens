import io,json
from unittest.mock import patch
from fastapi.testclient import TestClient
from paperlens.api import create_app
from paperlens.llm_transport import local_request
from paperlens.events import draft_text
from test_api import FakeEmbedder,make_pdf
def test_real_transport_delivers_chunks_before_final_result():
    chunks=[{"choices":[{"delta":{"content":'{"answerable":true,'},"finish_reason":None}]},{"choices":[{"delta":{"content":'"paragraphs":[]}'},"finish_reason":None}]},{"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"completion_tokens":10}}]
    stream=b"".join(b"data: "+json.dumps(c).encode()+b"\n\n" for c in chunks)+b"data: [DONE]\n\n"
    seen=[]
    with patch("urllib.request.urlopen",return_value=io.BytesIO(stream)):
        result=local_request({"stream":False},on_delta=seen.append)
    assert len(seen)==2 and json.loads(result["choices"][0]["message"]["content"])["answerable"]
    assert draft_text('{"text":"The study used 30')=="The study used 30"
def test_sse_result_is_persisted_and_followup_resolves_context(tmp_path):
    app=create_app(tmp_path,FakeEmbedder());client=TestClient(app)
    client.post("/api/documents",files={"file":("paper.pdf",make_pdf(),"application/pdf")})
    response=client.post("/api/ask/stream",json={"question":"What is curriculum learning?","mode":"lexical"})
    assert response.status_code==200 and "text/event-stream" in response.headers["content-type"]
    events=[line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    result=json.loads(events[-1]);cid=result["conversation_id"]
    assert result["status"]=="evidence"
    follow=client.post("/api/ask",json={"question":"How does it work?","mode":"lexical","conversation_id":cid}).json()
    assert "Previous question" in follow["resolved_question"]
    assert len(client.get("/api/conversations/"+cid).json()["turns"])==2
def test_protected_mode_roles_and_history_ownership(tmp_path):
    app=create_app(tmp_path,FakeEmbedder(),auth_required=True)
    app.state.auth.create_user("admin","TestPassword123!","admin")
    app.state.auth.create_user("viewer","TestPassword456!","viewer")
    admin=TestClient(app);viewer=TestClient(app)
    assert admin.get("/api/documents").status_code==401
    assert admin.post("/api/auth/login",json={"username":"admin","password":"TestPassword123!"}).status_code==200
    assert viewer.post("/api/auth/login",json={"username":"viewer","password":"TestPassword456!"}).status_code==200
    assert viewer.post("/api/index").status_code==403
    assert viewer.get("/api/metrics").status_code==403
    result=admin.post("/api/ask",json={"question":"What is in the paper?","mode":"lexical"}).json()
    cid=result["conversation_id"]
    assert viewer.get("/api/conversations/"+cid).status_code==404
    assert viewer.post("/api/ask/stream",json={"question":"Continue this.","conversation_id":cid}).status_code==404
    assert admin.post("/api/auth/logout").status_code==200
    assert admin.get("/api/conversations").status_code==401
