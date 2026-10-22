"""Persistence only: explicit transactions keep page text and embeddings together."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "papers").mkdir(exist_ok=True)
        self.db = self.folder / "paperlens.sqlite3"
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, source_url TEXT NOT NULL,
                    status TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL, pages INTEGER NOT NULL,
                    filename TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS chunks(
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                    page INTEGER NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL,
                    vector BLOB, model TEXT);
                CREATE TABLE IF NOT EXISTS document_pages(
                    document_id TEXT NOT NULL REFERENCES documents(id),page INTEGER NOT NULL,method TEXT NOT NULL,ocr_confidence REAL,
                    PRIMARY KEY(document_id,page));
                CREATE INDEX IF NOT EXISTS chunk_document ON chunks(document_id);
            """)
    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()
    def documents(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute("""
                SELECT d.*, COUNT(c.id) AS chunks, COUNT(c.vector) AS embedded_chunks
                FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                GROUP BY d.id ORDER BY d.created_at, d.id
            """)]
    def chunks(self, document_id=None):
        sql = """SELECT c.*, d.title, d.source_url, d.status, COALESCE(p.method,'text') AS extraction_method, p.ocr_confidence
                 FROM chunks c JOIN documents d ON d.id=c.document_id LEFT JOIN document_pages p ON p.document_id=c.document_id AND p.page=c.page"""
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                sql + (" WHERE d.id=?" if document_id else "") + " ORDER BY c.id",
                (document_id,) if document_id else ())]
    def document(self, doc_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            return dict(row) if row else None
