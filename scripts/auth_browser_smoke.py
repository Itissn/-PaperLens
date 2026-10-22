"""Real protected-mode UI using test-only accounts and a disposable database."""
import json,socket,tempfile,threading,time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright,expect
from paperlens.api import create_app
from paperlens.ingest import ingest_bytes,embed_pending
from paperlens.embeddings import Embedder
ROOT=Path(__file__).resolve().parents[1]
def main():
    with tempfile.TemporaryDirectory(prefix="paperlens-auth-",dir=ROOT/".cache") as temporary:
        encoder=Embedder(ROOT/".cache/embeddings")
        app=create_app(Path(temporary),encoder,auth_required=True)
        app.state.auth.create_user("browser_viewer","TestOnlyPassword123!","viewer")
        paper=json.loads((ROOT/"data/papers/manifest.json").read_text())[0]
        ingest_bytes(app.state.store,(ROOT/"data/papers"/paper["file"]).read_bytes(),paper["title"])
        embed_pending(app.state.store,encoder)
        with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="error"))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1280,"height":900})
                page.goto(f"http://127.0.0.1:{port}",wait_until="networkidle")
                expect(page.locator("#login-dialog")).to_be_visible()
                page.locator("#login-username").fill("browser_viewer")
                page.locator("#login-password").fill("TestOnlyPassword123!")
                page.locator("#login-form button").click()
                expect(page.locator("#login-dialog")).to_be_hidden()
                expect(page.locator("#identity-label")).to_contain_text("viewer")
                expect(page.locator("#pdf-upload")).to_be_disabled()
                expect(page.locator("#reindex")).to_be_hidden()
                page.locator("#mode").select_option("lexical")
                page.locator("#rerank").uncheck()
                page.locator("#question").fill("What does the study investigate?")
                page.locator("#ask").click()
                expect(page.locator("#results")).to_be_visible(timeout=30000)
                expect(page.locator(".conversation-open")).to_have_count(1)
                page.screenshot(path=str(ROOT/"reports/auth-browser.png"),full_page=True)
                page.locator("#sign-out").click()
                expect(page.locator("#login-dialog")).to_be_visible()
                assert page.request.get(f"http://127.0.0.1:{port}/api/conversations").status==401
                browser.close()
            report={"result":"passed","checks":["real cookie login UI","viewer upload/index restriction","SSE answer and private history","logout revocation"],"scope":"Disposable test account/database; real local embedding and PDF, no external deployment."}
            (ROOT/"reports/auth-browser-smoke.json").write_text(json.dumps(report,indent=2))
            print(json.dumps(report),flush=True)
        finally:
            server.should_exit=True;thread.join(timeout=5)
if __name__=="__main__":main()
