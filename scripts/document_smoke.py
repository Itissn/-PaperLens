"""Produce and inspect real raster/table/formula PDFs for the learner."""
import hashlib,json
from pathlib import Path
from paperlens.documents import extract_pdf,inspect_page,render_region
from scripts.sample_pdf import scanned_pdf,structured_pdf
ROOT=Path(__file__).resolve().parents[1]
def main():
    scan=scanned_pdf();structured=structured_pdf()
    pages=extract_pdf(scan,ocr=True);detail=inspect_page(structured,1)
    assert "30" in pages[0]["text"] and detail["tables"][0]["rows"][1][1]=="30"
    assert detail["formulas"][0]["symbolic"]["parsed"]
    reports=ROOT/"reports"
    (reports/"sample-scanned.pdf").write_bytes(scan)
    (reports/"sample-structured.pdf").write_bytes(structured)
    (reports/"sample-formula.png").write_bytes(render_region(structured,1,detail["formulas"][0]["bbox"]))
    report={"result":"passed","ocr":pages,"structure":detail,"synthetic_pdf_sha256":{"scanned":hashlib.sha256(scan).hexdigest(),"structured":hashlib.sha256(structured).hexdigest()},"scope":"Actual CPU OCR, PDF geometry table extraction, restricted symbolic parsing and PNG crop. No external OCR/model API."}
    (reports/"document-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"result":"passed","ocr_text":pages[0]["text"],"table":detail["tables"][0]["rows"],"formula":detail["formulas"][0]["symbolic"]}),flush=True)
if __name__=="__main__":main()
