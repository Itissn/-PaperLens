"""Optional local accounts. Hashed passwords, expiring hashed sessions and role checks."""
import hashlib,hmac,re,secrets,time,threading
from collections import defaultdict,deque
class Auth:
    def __init__(self,store,required=False):
        self.store=store;self.required=required;self.attempts=defaultdict(deque);self.lock=threading.Lock()
        with store.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,salt TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','viewer')));
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,expires_at REAL NOT NULL);
            """)
    def create_user(self,username,password,role="viewer"):
        if username.casefold()=="local":raise ValueError("This username is reserved for the desktop workspace.")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,64}",username):raise ValueError("Username must contain 3-64 letters, digits, dots, underscores or hyphens.")
        if len(password)<12 or len(password)>256:raise ValueError("Password must contain 12-256 characters.")
        if role not in ("admin","viewer"):raise ValueError("Unknown role.")
        salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),600000).hex()
        try:
            with self.store.connect() as con:con.execute("INSERT INTO users VALUES(?,?,?,?)",(username,salt,digest,role))
        except Exception as exc:
            import sqlite3
            if isinstance(exc,sqlite3.IntegrityError):raise ValueError("Username already exists.") from exc
            raise
        return {"username":username,"role":role}
    def login(self,username,password,client="local"):
        now=time.time()
        with self.lock:
            attempts=self.attempts[client]
            while attempts and attempts[0]<now-60:attempts.popleft()
            if len(attempts)>=5:raise PermissionError("Too many login attempts. Try again in one minute.")
            attempts.append(now)
        with self.store.connect() as con:row=con.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
        salt=bytes.fromhex(row["salt"]) if row else b"not-a-real-salt!"
        digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600000).hex()
        if not row or not hmac.compare_digest(digest,row["password_hash"]):raise ValueError("Invalid username or password.")
        token=secrets.token_urlsafe(32)
        with self.store.connect() as con:
            con.execute("DELETE FROM sessions WHERE expires_at<?",(now,))
            con.execute("INSERT INTO sessions VALUES(?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),username,now+28800))
        return token,{"username":username,"role":row["role"]}
    def identity(self,token):
        if not self.required:return {"username":"local","role":"admin","authentication_required":False}
        if not token:return None
        with self.store.connect() as con:
            row=con.execute("SELECT u.username,u.role FROM sessions s JOIN users u ON s.username=u.username WHERE s.token_hash=? AND s.expires_at>?",(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return {**dict(row),"authentication_required":True} if row else None
    def logout(self,token):
        if token:
            with self.store.connect() as con:con.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
