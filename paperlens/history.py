"""Owner-isolated persisted conversations; history is application data, not model memory."""
import json,re,time,uuid
class History:
    def __init__(self,store):
        self.store=store
        with store.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,question TEXT NOT NULL,resolved_question TEXT NOT NULL,response TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner,updated_at);
            """)
    def create(self,owner,title="New conversation"):
        cid=uuid.uuid4().hex;now=time.time()
        with self.store.connect() as con:con.execute("INSERT INTO conversations VALUES(?,?,?,?,?)",(cid,owner,title[:100],now,now))
        return self.get(owner,cid)
    def list(self,owner):
        with self.store.connect() as con:return [dict(r) for r in con.execute("SELECT c.*,COUNT(t.id) AS turn_count FROM conversations c LEFT JOIN turns t ON t.conversation_id=c.id WHERE c.owner=? GROUP BY c.id ORDER BY c.updated_at DESC LIMIT 100",(owner,))]
    def get(self,owner,cid):
        with self.store.connect() as con:
            row=con.execute("SELECT * FROM conversations WHERE id=? AND owner=?",(cid,owner)).fetchone()
            if not row:raise KeyError("Conversation not found.")
            turns=[{**dict(t),"response":json.loads(t["response"])} for t in con.execute("SELECT * FROM turns WHERE conversation_id=? ORDER BY id",(cid,))]
        return {**dict(row),"turns":turns}
    def add(self,owner,cid,question,resolved,response):
        with self.store.connect() as con:
            row=con.execute("SELECT id FROM conversations WHERE id=? AND owner=?",(cid,owner)).fetchone()
            if not row:raise KeyError("Conversation not found.")
            count=con.execute("SELECT COUNT(*) FROM turns WHERE conversation_id=?",(cid,)).fetchone()[0]
            if count>=50:raise ValueError("Conversation limit reached. Start a new conversation.")
            con.execute("INSERT INTO turns(conversation_id,question,resolved_question,response,created_at) VALUES(?,?,?,?,?)",(cid,question,resolved,json.dumps(response,ensure_ascii=False),time.time()))
            con.execute("UPDATE conversations SET updated_at=?,title=CASE WHEN ?=0 THEN ? ELSE title END WHERE id=?",(time.time(),count,question[:100],cid))
    def delete(self,owner,cid):
        with self.store.connect() as con:
            row=con.execute("DELETE FROM conversations WHERE id=? AND owner=?",(cid,owner))
            if not row.rowcount:raise KeyError("Conversation not found.")
def resolve_question(question,turns):
    # Only explicit contextual follow-ups inherit context; unrelated questions stand alone.
    followup=re.search(r"\b(it|its|they|their|them|those|that|these|same)\b",question,re.I) or re.match(r"\s*(and\b|what about\b|how about\b)",question,re.I)
    if not turns or not followup:return question
    previous=turns[-1]
    titles=list(dict.fromkeys(c["title"] for c in previous["response"].get("citations",[])))[:2]
    context="; ".join(titles) or previous["question"][:300]
    return "Context: "+context[:400]+". Previous question: "+previous["question"][:200]+". Follow-up: "+question
