import io
import pytest
from pypdf import PdfWriter
from paperlens.ingest import ingest_bytes,split_page
from paperlens.store import Store

def test_page_chunks_overlap_and_boundary():
    chunks=list(split_page(" ".join(str(i) for i in range(240)),size=120,overlap=25))
    assert len(chunks)==3
    assert chunks[0].split()[-25:]==chunks[1].split()[:25]
    assert chunks[-1].split()[-1]=="239"
    with pytest.raises(ValueError): list(split_page("hi",size=120,overlap=120))

def test_reject_invalid_and_scanned_pdf(tmp_path):
    store=Store(tmp_path)
    with pytest.raises(ValueError,match="valid PDF"): ingest_bytes(store,b"hello","bad")
    writer=PdfWriter(); writer.add_blank_page(width=300,height=300)
    out=io.BytesIO(); writer.write(out)
    with pytest.raises(ValueError,match="OCR"): ingest_bytes(store,out.getvalue(),"scan")
    assert store.documents()==[]


def test_sqlite_connections_are_closed_after_context(tmp_path):
    import sqlite3
    store=Store(tmp_path)
    with store.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0]==1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
