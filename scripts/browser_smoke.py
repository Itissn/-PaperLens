"""Real browser smoke test against a disposable app service; uses local real embeddings.
No personal Chrome profile and no paid calls.
"""
import json
import re
import socket
import threading
import tempfile
import time
from pathlib import Path
import uvicorn
from playwright.sync_api import sync_playwright,expect
from paperlens.api import create_app
from paperlens.store import Store
from paperlens.ingest import ingest_bytes,embed_pending
from paperlens.embeddings import Embedder

ROOT=Path(__file__).resolve().parents[1]

def main():
    errors=[]
    reports=ROOT/"reports";reports.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="paperlens-browser-",dir=ROOT/".cache") as temporary:
        data=Path(temporary)
        store=Store(data)
        manifest=json.loads((ROOT/"data"/"papers"/"manifest.json").read_text(encoding="utf-8"))
        for paper in manifest:
            ingest_bytes(store,(ROOT/"data"/"papers"/paper["file"]).read_bytes(),paper["title"],paper["source_url"],paper["status"])
        encoder=Embedder(ROOT/".cache"/"embeddings")
        embed_pending(store,encoder)
        with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(create_app(data,encoder),host="127.0.0.1",port=port,log_level="warning"))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1440,"height":1050},device_scale_factor=1)
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{port}",wait_until="networkidle")
                expect(page.locator(".doc-card")).to_have_count(3)
                assert page.locator("html").get_attribute("lang")=="en"
                assert not re.search(r"[\u3400-\u9fff]",page.locator("body").inner_text())
                expect(page.locator("#stats")).to_contain_text("146")
                page.locator('[data-question]').first.click()
                page.locator("#ask").click()
                expect(page.locator("#answer-status")).to_have_text("EXTRACTIVE",timeout=30000)
                expect(page.locator(".support-check").first).to_be_visible()
                with page.expect_download() as download_event:
                    page.locator("#export-result").click()
                saved=reports/"browser-export.json"
                download_event.value.save_as(str(saved))
                exported=json.loads(saved.read_text(encoding="utf-8"))
                assert exported["response"]["retrieval"]["rerank"]["enabled"]
                expect(page.locator(".citation").first).to_be_visible()
                assert "#page=" in page.locator(".citation").first.get_attribute("href")
                page.locator(".evidence-card details").first.click()
                expect(page.locator(".evidence-card details p").first).to_be_visible()
                expect(page.locator(".conversation-open")).to_have_count(1)
                first_cid=page.evaluate("lastResult.response.conversation_id")
                page.locator("#new-conversation").click()
                expect(page.locator("#results")).to_be_hidden()
                page.locator(".conversation-open").first.click()
                expect(page.locator(".turn-button")).to_have_count(1)
                page.locator("#question").fill("How does it estimate difficulty?")
                page.locator("#ask").click()
                expect(page.locator(".turn-button")).to_have_count(2,timeout=30000)
                assert page.evaluate("lastResult.response.conversation_id")==first_cid
                assert "Context:" in page.evaluate("lastResult.response.resolved_question")
                page.reload(wait_until="networkidle")
                page.locator(".conversation-open").first.click()
                expect(page.locator(".turn-button")).to_have_count(2)
                page.locator(".doc-links button").nth(1).click()
                expect(page.locator("#structure-content")).to_contain_text("Formula candidates",timeout=30000)
                expect(page.locator(".page-preview")).to_be_visible()
                page.locator("#close-structure").click()
                page.screenshot(path=str(reports/"desktop.png"),full_page=True)
                page.locator("#question").fill("How does DCL-GPGLS estimate instance difficulty?")
                page.locator("#compare").click()
                expect(page.locator(".compare-column")).to_have_count(4,timeout=30000)
                page.locator('[data-panel="evaluation"]').click()
                expect(page.locator("#eval-content tbody tr")).to_have_count(4)
                expect(page.locator(".eval-case")).to_have_count(15)
                expect(page.locator(".challenge-case")).to_have_count(8)
                assert not re.search(r"[\u3400-\u9fff]",page.locator("body").inner_text())
                page.locator('[data-panel="learn"]').click()
                expect(page.locator(".learning-flow article")).to_have_count(4)
                assert not re.search(r"[\u3400-\u9fff]",page.locator("body").inner_text())
                page.locator('[data-panel="workspace"]').click()
                page.locator(".doc-links button").first.click()
                expect(page.locator("#chunk-dialog")).to_be_visible()
                assert page.locator(".chunk-item").count()>0
                page.locator("#close-dialog").click()
                # Unsupported question must show why generation was withheld.
                page.locator("#question").fill("What is the current mortgage interest rate at BNZ?")
                page.locator("#ask").click()
                expect(page.locator("#answer-status")).to_have_text("EVIDENCE INSUFFICIENT",timeout=30000)
                expect(page.locator("#evidence-assessment")).to_contain_text("No passage met")
                # Workflow controls expose the agent's actual tool policy.
                page.locator("#workflow").select_option("agent")
                expect(page.locator("#mode")).to_be_disabled()
                expect(page.locator("#scope")).to_be_disabled()
                expect(page.locator("#generator")).to_have_value("local_llm")
                page.locator("#workflow").select_option("rag")
                # Duplicate upload must preserve all corpus counts.
                page.locator("#pdf-upload").set_input_files(str(ROOT/"data"/"papers"/manifest[0]["file"]))
                expect(page.locator("#alert")).to_contain_text("already exists",timeout=30000)
                expect(page.locator(".doc-card")).to_have_count(3)
                page.locator("#pdf-upload").set_input_files({"name":"bad.pdf","mimeType":"application/pdf","buffer":b"not a pdf"})
                expect(page.locator("#alert")).to_contain_text("valid PDF")
                page.set_viewport_size({"width":390,"height":844})
                page.locator("#alert").evaluate("(e)=>e.hidden=true")
                page.evaluate("window.scrollTo(0,0)")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                expect(page.locator("#ask")).to_be_visible()
                page.screenshot(path=str(reports/"mobile.png"),full_page=True)
                assert not errors,errors
                browser.close()
            report={"result":"passed","browser":"Chrome headless, isolated profile","checks":["library","real retrieval","citation page link","evidence expansion","four-strategy comparison","source support display","English interface and feedback","persisted conversations","contextual follow-up","history after reload","structured page inspection","SSE progress/result","JSON export","unsupported-question refusal","agent controls","evaluation","learning view","chunk inspector","duplicate PDF","invalid PDF","mobile overflow","no uncaught JS errors"],"screenshots":["desktop.png","mobile.png"]}
            (reports/"browser-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
            print(json.dumps(report,indent=2))
        finally:
            server.should_exit=True;thread.join(timeout=5)
if __name__=="__main__":main()
