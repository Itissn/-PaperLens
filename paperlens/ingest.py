"""PDF -> page-preserving chunks. PDF page is physical 1-based page, not printed folio."""
import hashlib
import io
import re
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
CHUNK_WORDS = 120
OVERLAP_WORDS = 25

def clean_text(text):
    text = re.sub(r"([A-Za-z])-\s*\n\s*([a-z])", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()

def split_page(text, size=CHUNK_WORDS, overlap=OVERLAP_WORDS):
    if size < 20 or not 0 <= overlap < size:
        raise ValueError("Chunk size must be >=20 and overlap smaller than size.")
    words = clean_text(text).split()
    for start in range(0, len(words), size-overlap):
        chunk = " ".join(words[start:start+size])
        if chunk: yield chunk
        if start+size >= len(words): break

def ingest_bytes(store, data, title, source_url="", status="User-uploaded PDF", chunk_words=CHUNK_WORDS, overlap_words=OVERLAP_WORDS,ocr=False):
    if not data.startswith(b"%PDF") or len(data) > MAX_BYTES:
        raise ValueError("Upload a valid PDF of at most 20 MB.")
    digest = hashlib.sha256(data).hexdigest()
    doc_id = digest[:20]
    existing = store.document(doc_id)
    if existing:
        return {**existing, "duplicate": True}
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        if not 0 < len(reader.pages) <= 200:
            raise ValueError("PDF must contain 1–200 pages.")
        chunks = []
        page_metadata=[]
        if ocr:
            from .documents import extract_pdf
            extracted_pages=extract_pdf(data,ocr=True)
        extracted = 0
        for number, page in enumerate(reader.pages, 1):
            if ocr:
                record=extracted_pages[number-1];text=record["text"]
                page_metadata.append((doc_id,number,record["method"],record["ocr_confidence"]))
            else:
                text = page.extract_text() or ""
                page_metadata.append((doc_id,number,"text",None))
            extracted += len(text)
            if extracted > 2_000_000:
                raise ValueError("PDF text exceeds the learning project's limit.")
            for position, chunk in enumerate(split_page(text,chunk_words,overlap_words)):
                chunks.append((f"{doc_id}-{number}-{position}", doc_id, number, position, chunk))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be parsed. Please export a fresh text PDF.") from exc
    if sum(len(c[-1]) for c in chunks) < (20 if ocr else 80):
        raise ValueError("No usable text found. Enable OCR for image PDFs; blank pages cannot be indexed.")
    # User filenames never become filesystem paths.
    filename = doc_id + ".pdf"
    path = store.folder / "papers" / filename
    path.write_bytes(data)
    try:
        with store.connect() as con:
            con.execute("INSERT INTO documents(id,title,source_url,status,sha256,pages,filename) VALUES(?,?,?,?,?,?,?)",
                        (doc_id, title[:300], source_url, status, digest, len(reader.pages), filename))
            con.executemany("INSERT INTO chunks(id,document_id,page,position,text) VALUES(?,?,?,?,?)", chunks)
            con.executemany("INSERT INTO document_pages VALUES(?,?,?,?)",page_metadata)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {**store.document(doc_id), "duplicate": False}

def embed_pending(store, embedder):
    rows = [r for r in store.chunks() if r["model"] != embedder.name or r["vector"] is None]
    if not rows: return 0
    vectors = embedder.documents([r["text"] for r in rows])
    if len(vectors) != len(rows):
        raise ValueError("Embedding count mismatch.")
    with store.connect() as con:
        con.executemany("UPDATE chunks SET vector=?,model=? WHERE id=?",
                        [(v.astype("<f4").tobytes(), embedder.name, r["id"]) for r,v in zip(rows,vectors)])
    return len(rows)
