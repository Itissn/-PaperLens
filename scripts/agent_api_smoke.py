"""Exercise real native model tool calls through the live browser and HTTP API.
Requires Start.cmd. Uses isolated headless Chrome, no personal profile.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
def main():
    errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="chrome",headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1050})
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto("http://127.0.0.1:8765",wait_until="networkidle")
        page.locator("#workflow").select_option("agent")
        page.locator("#question").fill("How many random seeds were used in the BN-GPGLS experiments? Search the papers and inspect the relevant page.")
        page.locator("#ask").click()
        expect(page.locator("#agent-trace")).to_be_visible(timeout=240000)
        data=page.evaluate("lastResult")
        result=data["response"]; trace=result["agent"]["trace"]
        assert result["status"]=="generated",result
        assert result["agent"]["page_verification"]
        assert result["agent"]["all_cited_pages_read"]
        assert result["semantic_check"]["passed"]
        assert any(s["tool"]=="search_papers" and s["outcome"]=="ok" for s in trace)
        assert any(s["tool"]=="read_page" and s["outcome"]=="ok" for s in trace)
        assert "30" in " ".join(p["text"] for p in result["paragraphs"])
        assert result["validation"]["passed"]
        assert result["usage"]["output_tokens"]>0
        assert any(h["page"]==8 for h in result["citations"])
        assert not errors,errors
        page.locator(".agent-step").nth(1).locator("summary").click()
        page.screenshot(path=str(ROOT/"reports"/"agent-browser.png"),full_page=True)
        report={"version":"0.3.0","entrypoint":"Browser -> POST /api/agent/stream -> real native Qwen tool calls","question":data["query"]["question"],"result":result,"browser_errors":errors,"manual_review":"Seed-count answer 30 matches the source protocol on physical PDF page 8; this single case is not an accuracy benchmark."}
        (ROOT/"reports"/"agent-api-smoke.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({"status":result["status"],"model":result["model"],"tools":[{"name":s["tool"],"args":s["arguments"],"outcome":s["outcome"]} for s in trace],"paragraphs":result["paragraphs"],"usage":result["usage"],"total_latency_ms":result["total_latency_ms"]},indent=2),flush=True)
        browser.close()
if __name__=="__main__":main()
