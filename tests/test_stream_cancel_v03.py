import socket,threading,time
import httpx,uvicorn
from paperlens.api import create_app
from paperlens.ingest import ingest_bytes,embed_pending
from test_api import FakeEmbedder,make_pdf
def test_disconnected_stream_cancels_and_does_not_save_partial_turn(tmp_path,monkeypatch):
    import paperlens.api as module
    app=create_app(tmp_path,FakeEmbedder())
    ingest_bytes(app.state.store,make_pdf(),"Paper");embed_pending(app.state.store,FakeEmbedder())
    entered=threading.Event();finished=threading.Event()
    def slow_answer(query,hits,generator,ranker=None,emit=None):
        entered.set()
        try:
            for i in range(80):
                emit("draft",{"text":"Partial answer "+str(i),"verified":False});time.sleep(.025)
        finally:finished.set()
        raise AssertionError("A cancelled stream must not reach persistence")
    monkeypatch.setattr(module,"answer",slow_answer)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.01)
        with httpx.Client(timeout=10) as client:
            with client.stream("POST",f"http://127.0.0.1:{port}/api/ask/stream",json={"question":"What is curriculum learning?","mode":"lexical"}) as response:
                for line in response.iter_lines():
                    if line=="event: draft":break
        assert entered.wait(2) and finished.wait(3)
        conversations=app.state.history.list("local")
        assert len(conversations)==1 and conversations[0]["turn_count"]==0
    finally:
        server.should_exit=True;thread.join(timeout=3)
