from paperlens.documents import extract_pdf,inspect_page,render_region
from scripts.sample_pdf import scanned_pdf,structured_pdf
def test_real_ocr_reads_raster_pdf():
    data=scanned_pdf()
    assert extract_pdf(data,ocr=False)[0]["text"].strip()==""
    pages=extract_pdf(data,ocr=True)
    assert "30" in pages[0]["text"] and "random seeds" in pages[0]["text"].lower()
    assert pages[0]["method"]=="ocr"
def test_real_table_cells_formula_region_and_crop():
    data=structured_pdf();result=inspect_page(data,1)
    assert result["tables"][0]["rows"]==[["Method","Seeds"],["Baseline","30"]]
    assert any("f(x)" in x["text"] for x in result["formulas"])
    assert result["formulas"][0]["symbolic"]["parsed"]
    assert render_region(data,1,result["formulas"][0]["bbox"]).startswith(b"\x89PNG")
def test_scanned_upload_is_indexed_and_retrievable(tmp_path):
    from fastapi.testclient import TestClient
    from paperlens.api import create_app
    from test_api import FakeEmbedder
    app=create_app(tmp_path,FakeEmbedder());client=TestClient(app)
    response=client.post("/api/documents",files={"file":("scanned.pdf",scanned_pdf(),"application/pdf")},data={"ocr":"true"})
    assert response.status_code==200,response.text
    doc=response.json()["document"]
    with app.state.store.connect() as con:
        assert con.execute("SELECT method FROM document_pages WHERE document_id=?",(doc["id"],)).fetchone()[0]=="ocr"
    result=client.post("/api/ask",json={"question":"How many random seeds?","mode":"lexical"}).json()
    assert result["status"]=="evidence" and "30" in result["paragraphs"][0]["text"]
