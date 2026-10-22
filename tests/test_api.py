import io
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,NameObject,DictionaryObject
from paperlens.api import create_app
from paperlens.ingest import embed_pending,ingest_bytes
from paperlens.retrieval import Retriever

class FakeEmbedder:
    name="test-encoder"
    def documents(self,texts): return np.array([[1,0,0] for _ in texts],dtype=np.float32)
    def query(self,text): return np.array([1,0,0],dtype=np.float32)

def make_pdf():
    writer=PdfWriter()
    for i in range(2):
        page=writer.add_blank_page(600,800)
        font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream=DecodedStreamObject()
        text=("Curriculum learning orders training examples by difficulty. Routing optimization uses guided local search. "*3)
        stream.set_data(f"BT /F1 12 Tf 30 600 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")]=writer._add_object(stream)
    out=io.BytesIO(); writer.write(out); return out.getvalue()

def test_upload_search_page_citation_duplicate_and_restart(tmp_path):
    app=create_app(tmp_path,FakeEmbedder()); client=TestClient(app)
    data=make_pdf()
    response=client.post("/api/documents",files={"file":("../../unsafe.pdf",data,"application/pdf")})
    assert response.status_code==200,response.text
    doc=response.json()["document"]; doc_id=doc["id"]
    assert doc["filename"]==doc_id+".pdf"
    assert not (tmp_path.parent/"unsafe.pdf").exists()
    duplicate=client.post("/api/documents",files={"file":("same.pdf",data,"application/pdf")}).json()
    assert duplicate["document"]["duplicate"] is True
    assert len(client.get("/api/documents").json())==1
    result=client.post("/api/ask",json={"question":"What is curriculum learning?","mode":"hybrid"}).json()
    assert result["status"]=="evidence"
    assert result["citations"][0]["page"] in [1,2]
    assert client.get(f"/api/documents/{doc_id}/pdf").content.startswith(b"%PDF")
    restarted=TestClient(create_app(tmp_path,FakeEmbedder()))
    assert restarted.get("/api/status").json()["embedded_chunks"]==2
    assert restarted.post("/api/search",json={"question":"curriculum","mode":"semantic"}).json()["hits"]

def test_validation_origin_and_error_paths(tmp_path):
    client=TestClient(create_app(tmp_path,FakeEmbedder()))
    assert client.post("/api/ask",json={"question":"   "}).status_code==422
    assert client.post("/api/ask",json={"question":"routing","k":99}).status_code==422
    assert client.post("/api/ask",json={"question":"routing","mode":"fake"}).status_code==422
    assert client.post("/api/index",headers={"Origin":"https://evil.example"}).status_code==403
    assert client.get("/api/documents/../pdf").status_code==404
    assert client.post("/api/documents",files={"file":("bad.pdf",b"no","application/pdf")}).status_code==400

def test_incomplete_index_error_and_repair(tmp_path):
    app=create_app(tmp_path,FakeEmbedder()); client=TestClient(app)
    ingest_bytes(app.state.store,make_pdf(),"Needs vectors")
    assert client.post("/api/search",json={"question":"routing","mode":"semantic"}).status_code==409
    assert client.post("/api/index").status_code==200
    assert client.post("/api/search",json={"question":"routing","mode":"hybrid"}).status_code==200


def test_lexical_api_does_not_need_to_load_an_embedding_model(tmp_path):
    from unittest.mock import patch
    app=create_app(tmp_path)
    ingest_bytes(app.state.store,make_pdf(),"BM25 only")
    with patch("paperlens.api.Embedder",side_effect=AssertionError("must not load")):
        response=TestClient(app).post("/api/search",json={"question":"curriculum learning","mode":"lexical"})
    assert response.status_code==200
    assert response.json()["hits"]


def test_optional_reranker_drives_visible_evidence_refusal(tmp_path):
    class Negative:
        name="fake-negative"
        def score(self,q,texts):return [-5.0]*len(texts)
    app=create_app(tmp_path,FakeEmbedder(),Negative())
    ingest_bytes(app.state.store,make_pdf(),"Known corpus")
    embed_pending(app.state.store,FakeEmbedder())
    result=TestClient(app).post("/api/ask",json={"question":"Does this mention hospitals?","rerank":True,"generator":"local_llm"})
    assert result.status_code==200
    assert result.json()["status"]=="abstained"
    assert result.json()["evidence_assessment"]["reason"]=="below_reranker_cutoff"
    assert result.json()["retrieval"]["rerank"]["enabled"]
