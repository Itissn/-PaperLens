"""Local API: validated retrieval, persisted conversations, streaming and optional accounts."""
import asyncio,json,os,queue,threading,time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,HTTPException,UploadFile,Request,Form,Response
from fastapi.responses import FileResponse,JSONResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .store import Store
from .embeddings import Embedder,MODEL
from .reranking import Reranker,MODEL as RERANK_MODEL,RELEVANCE_CUTOFF
from .ingest import ingest_bytes,embed_pending,MAX_BYTES
from .retrieval import Retriever
from .answer import answer,GenerationError
from .history import History,resolve_question
from .auth import Auth
from .events import encode_event
ROOT=Path(__file__).resolve().parents[1]
class Query(BaseModel):
    question:str=Field(min_length=3,max_length=600)
    mode:Literal["lexical","semantic","hybrid"]="hybrid"
    k:int=Field(default=5,ge=1,le=10)
    rerank:bool=False
    document_id:str|None=Field(default=None,pattern=r"^[a-f0-9]{20}$")
    generator:Literal["extractive","ollama","local_llm"]="extractive"
    conversation_id:str|None=Field(default=None,pattern=r"^[a-f0-9]{32}$")
    @field_validator("question")
    @classmethod
    def valid_question(cls,value):
        if len(value.strip())<3:raise ValueError("Please enter a specific question.")
        return value.strip()
class Login(BaseModel):
    username:str=Field(min_length=3,max_length=64)
    password:str=Field(min_length=1,max_length=256)
class NewUser(Login):
    role:Literal["admin","viewer"]="viewer"
def create_app(data_dir=None,embedder=None,reranker=None,auth_required=None):
    app=FastAPI(title="PaperLens",version="0.3.0",description="Local paper research, source checks and bounded tool calling.")
    hosts=[x.strip() for x in os.environ.get("PAPERLENS_ALLOWED_HOSTS","127.0.0.1,localhost,testserver").split(",") if x.strip()]
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
    store=Store(Path(data_dir) if data_dir else ROOT/"data")
    history=History(store)
    auth=Auth(store,os.environ.get("PAPERLENS_AUTH_REQUIRED")=="1" if auth_required is None else auth_required)
    lock=threading.RLock();metrics_lock=threading.Lock();capacity=threading.BoundedSemaphore(2)
    metrics={"requests":0,"server_errors":0,"request_seconds":0.0,"active_jobs":0}
    state={"embedder":embedder,"reranker":reranker}
    app.state.store=store;app.state.auth=auth;app.state.history=history
    def engine():
        if state["embedder"] is None:state["embedder"]=Embedder(ROOT/".cache"/"embeddings")
        return state["embedder"]
    def ranking_engine():
        if state["reranker"] is None:state["reranker"]=Reranker(ROOT/".cache"/"reranker")
        return state["reranker"]
    def identity(request):return request.state.identity
    def admin(request):
        if identity(request)["role"]!="admin":raise HTTPException(403,"Administrator permission required.")
    @app.middleware("http")
    async def boundary(request,call_next):
        started=time.perf_counter()
        origin=request.headers.get("origin")
        if request.method not in ("GET","HEAD","OPTIONS") and origin and origin!=f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse(status_code=403,content={"detail":"Cross-origin writes are disabled."})
        who=auth.identity(request.cookies.get("paperlens_session"))
        public=request.url.path in ("/","/api/auth/login","/api/health","/api/readiness") or request.url.path.startswith("/static/")
        if not who and not public:return JSONResponse(status_code=401,content={"detail":"Sign in to continue."})
        request.state.identity=who
        response=await call_next(request)
        response.headers.update({"X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        with metrics_lock:
            metrics["requests"]+=1;metrics["server_errors"]+=int(response.status_code>=500);metrics["request_seconds"]+=time.perf_counter()-started
        return response
    @app.get("/api/auth/me")
    def me(request:Request):return identity(request)
    @app.post("/api/auth/login")
    def login(body:Login,request:Request):
        try:token,who=auth.login(body.username,body.password,request.client.host if request.client else "local")
        except PermissionError as exc:raise HTTPException(429,str(exc))
        except ValueError as exc:raise HTTPException(401,str(exc))
        response=JSONResponse({**who,"authentication_required":auth.required})
        response.set_cookie("paperlens_session",token,max_age=28800,httponly=True,samesite="strict",secure=os.environ.get("PAPERLENS_COOKIE_SECURE")=="1")
        return response
    @app.post("/api/auth/logout")
    def logout(request:Request):
        auth.logout(request.cookies.get("paperlens_session"))
        response=JSONResponse({"signed_out":True});response.delete_cookie("paperlens_session");return response
    @app.post("/api/admin/users")
    def create_user(body:NewUser,request:Request):
        admin(request)
        try:return auth.create_user(body.username,body.password,body.role)
        except ValueError as exc:raise HTTPException(400,str(exc))
    @app.get("/api/health")
    def health():return {"status":"ok","version":"0.3.0","authentication_required":auth.required}
    @app.get("/api/readiness")
    def readiness():
        if os.environ.get("PAPERLENS_STRICT_READINESS")=="1":
            from .deployment import deployment_status
            result=deployment_status(store,ROOT)
            if not auth.required:
                result["checks"]["authentication"]=False
                result["ready"]=False
            return JSONResponse(status_code=200 if result["ready"] else 503,content=result)
        try:
            with store.connect() as con:con.execute("SELECT 1").fetchone()
            return {"ready":True,"database":"ok","semantic_model_available":(ROOT/".cache/nli/provenance.json").exists()}
        except Exception:return JSONResponse(status_code=503,content={"ready":False,"database":"unavailable"})
    @app.get("/api/metrics")
    def runtime_metrics(request:Request):
        admin(request)
        with metrics_lock:return {**metrics,"scope":"Process-local request counters and active jobs. No question text, passwords or tokens."}
    @app.get("/api/status")
    def status():
        docs=store.documents()
        return {"documents":len(docs),"chunks":sum(d["chunks"] for d in docs),"embedded_chunks":sum(d["embedded_chunks"] for d in docs),"embedding_model":MODEL,"generator_default":"extractive","version":"0.3.0","reranker_model":RERANK_MODEL,"reranker_cutoff":RELEVANCE_CUTOFF,"ollama_configured":bool(os.environ.get("PAPERLENS_OLLAMA_MODEL")),"local_llm_configured":bool(os.environ.get("PAPERLENS_LLM_BASE_URL")) or (ROOT/".cache/local-llm/provenance.json").exists(),"semantic_model_available":(ROOT/".cache/nli/provenance.json").exists(),"language_note":"English model/corpus; cross-language retrieval is not evaluated.","authentication_required":auth.required}
    @app.get("/api/documents")
    def documents():return store.documents()
    def existing(doc_id):
        doc=store.document(doc_id)
        if not doc:raise HTTPException(404,"Document not found.")
        return doc
    @app.get("/api/documents/{doc_id}/pdf")
    def pdf(doc_id:str):
        doc=existing(doc_id)
        return FileResponse(store.folder/"papers"/doc["filename"],media_type="application/pdf",content_disposition_type="inline",filename=doc["filename"])
    @app.get("/api/documents/{doc_id}/chunks")
    def chunks(doc_id:str):
        existing(doc_id)
        return [{k:v for k,v in r.items() if k not in ("vector","model")} for r in store.chunks(doc_id)]
    @app.get("/api/documents/{doc_id}/pages/{number}/structure")
    def structure(doc_id:str,number:int,ocr:bool=False):
        from .documents import inspect_page
        doc=existing(doc_id)
        try:
            with lock:return inspect_page((store.folder/"papers"/doc["filename"]).read_bytes(),number,ocr)
        except ValueError as exc:raise HTTPException(400,str(exc))
    @app.get("/api/documents/{doc_id}/pages/{number}/image")
    def page_image(doc_id:str,number:int,bbox:str|None=None):
        from .documents import render_region
        import math
        doc=existing(doc_id)
        try:
            box=[float(x) for x in bbox.split(",")] if bbox else None
            if box and (len(box)!=4 or any(not math.isfinite(x) for x in box)):raise ValueError("Invalid page region.")
            with lock:data=render_region((store.folder/"papers"/doc["filename"]).read_bytes(),number,box)
            return Response(data,media_type="image/png")
        except ValueError as exc:raise HTTPException(400,str(exc))
    @app.post("/api/documents")
    def upload(request:Request,file:UploadFile,ocr:bool=Form(False)):
        admin(request)
        data=file.file.read(MAX_BYTES+1);title=Path((file.filename or "Uploaded paper").replace("\\","/")).stem[:300]
        with lock:
            try:doc=ingest_bytes(store,data,title,ocr=ocr)
            except ValueError as exc:raise HTTPException(400,str(exc))
            try:count=embed_pending(store,engine())
            except Exception:raise HTTPException(503,"PDF saved; embeddings are not ready. Fix model setup then repair the index.")
        return {"document":doc,"embedded_chunks":count}
    @app.post("/api/index")
    def rebuild_index(request:Request):
        admin(request)
        with lock:
            try:return {"embedded_chunks":embed_pending(store,engine())}
            except Exception:raise HTTPException(503,"Embedding model unavailable. Check local model cache and server log.")
    @app.get("/api/conversations")
    def conversations(request:Request):return history.list(identity(request)["username"])
    @app.get("/api/conversations/{cid}")
    def conversation(cid:str,request:Request):
        try:return history.get(identity(request)["username"],cid)
        except KeyError:raise HTTPException(404,"Conversation not found.")
    @app.delete("/api/conversations/{cid}")
    def delete_conversation(cid:str,request:Request):
        try:history.delete(identity(request)["username"],cid);return {"deleted":True}
        except KeyError:raise HTTPException(404,"Conversation not found.")
    def retrieve(q):
        try:return Retriever(store,state["embedder"] if q.mode=="lexical" else engine(),ranking_engine() if q.rerank else None).search(q.question,q.mode,q.k,q.document_id,rerank=q.rerank)
        except ValueError as exc:raise HTTPException(409,str(exc))
        except Exception:raise HTTPException(503,"Retrieval model unavailable. Check model setup and logs.")
    def run_query(q,workflow,owner,emit=None,cancel=None):
        started=time.perf_counter()
        with lock:
            if cancel and cancel.is_set():raise GenerationError("Request cancelled.")
            try:c=history.get(owner,q.conversation_id) if q.conversation_id else history.create(owner)
            except KeyError:raise HTTPException(404,"Conversation not found.")
            if len(c["turns"])>=50:raise HTTPException(409,"Conversation limit reached. Start a new conversation.")
            resolved=resolve_question(q.question,c["turns"])
            if emit:emit("started",{"conversation_id":c["id"],"resolved_question":resolved})
            if workflow=="agent":
                from .agent import PaperAgent
                response=PaperAgent(store,engine(),ranking_engine()).run(resolved,q.generator,emit=emit)
            else:
                if emit:emit("retrieval",{"message":"Searching the local paper library."})
                result=retrieve(q.model_copy(update={"question":resolved}))
                if q.rerank:
                    from .quality import expand_definitions
                    result["hits"]=expand_definitions(store,resolved,result["hits"],ranking_engine())
                if emit:emit("evidence",{"passages":len(result["hits"]),"latency_ms":result["latency_ms"]})
                response={**answer(resolved,result["hits"],q.generator,ranker=ranking_engine() if q.rerank else None,emit=emit),"retrieval":result,"total_latency_ms":round((time.perf_counter()-started)*1000,2)}
            if cancel and cancel.is_set():raise GenerationError("Request cancelled.")
            response.update(conversation_id=c["id"],resolved_question=resolved,original_question=q.question)
            history.add(owner,c["id"],q.question,resolved,response)
            return response
    def limited_query(q,workflow,owner):
        if not capacity.acquire(blocking=False):raise HTTPException(429,"Research capacity reached. Try again after a task finishes.")
        try:return run_query(q,workflow,owner)
        finally:capacity.release()
    @app.post("/api/search")
    def search(q:Query):
        with lock:return retrieve(q)
    @app.post("/api/ask")
    def ask(q:Query,request:Request):
        try:return limited_query(q,"rag",identity(request)["username"])
        except GenerationError as exc:raise HTTPException(503,str(exc))
    @app.post("/api/agent")
    def agent_run(q:Query,request:Request):
        try:return limited_query(q,"agent",identity(request)["username"])
        except GenerationError as exc:raise HTTPException(503,str(exc))
    def stream_response(q,workflow,request):
        owner=identity(request)["username"]
        if q.conversation_id:
            try:history.get(owner,q.conversation_id)
            except KeyError:raise HTTPException(404,"Conversation not found.")
        if not capacity.acquire(blocking=False):raise HTTPException(429,"Research capacity reached. Try again after a task finishes.")
        events=queue.Queue(maxsize=128);cancel=threading.Event()
        def emit(event,data):
            if cancel.is_set():raise GenerationError("Request cancelled.")
            if event=="draft" and events.qsize()>100:return
            while not cancel.is_set():
                try:events.put((event,data),timeout=.2);return
                except queue.Full:continue
            raise GenerationError("Request cancelled.")
        def worker():
            with metrics_lock:metrics["active_jobs"]+=1
            try:emit("result",run_query(q,workflow,owner,emit,cancel))
            except Exception as exc:
                if not isinstance(exc,(HTTPException,GenerationError)):
                    import logging
                    logging.getLogger("paperlens").exception("Research worker failed")
                if not cancel.is_set():
                    message=str(exc.detail) if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,GenerationError) else "The research task failed. Check the server log."
                    emit("error",{"message":message})
            finally:
                with metrics_lock:metrics["active_jobs"]-=1
                capacity.release()
        threading.Thread(target=worker,daemon=True).start()
        async def output():
            try:
                while not cancel.is_set():
                    if await request.is_disconnected():break
                    try:event,data=await asyncio.to_thread(events.get,True,.5)
                    except queue.Empty:
                        yield ": heartbeat\n\n";continue
                    yield encode_event(event,data)
                    if event in ("result","error"):break
            finally:cancel.set()
        return StreamingResponse(output(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
    @app.post("/api/ask/stream")
    def ask_stream(q:Query,request:Request):return stream_response(q,"rag",request)
    @app.post("/api/agent/stream")
    def agent_stream(q:Query,request:Request):return stream_response(q,"agent",request)
    @app.get("/api/evaluation")
    def evaluation():
        report=ROOT/"reports/retrieval-evaluation.json"
        if not report.exists():raise HTTPException(404,"Run evaluation first.")
        return FileResponse(report,media_type="application/json")
    @app.get("/api/evaluation/challenge")
    def challenge_evaluation():
        report=ROOT/"reports/challenge-evaluation.json"
        if not report.exists():raise HTTPException(404,"Run challenge evaluation first.")
        return FileResponse(report,media_type="application/json")
    @app.get("/")
    def home():return FileResponse(ROOT/"web/index.html")
    app.mount("/static",StaticFiles(directory=ROOT/"web"),name="static")
    return app
app=create_app()
