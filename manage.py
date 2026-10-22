"""CLI: ingest fixed public corpus, rebuild vectors, inspect status, run app."""
import argparse
import json
from pathlib import Path
from paperlens.store import Store
from paperlens.ingest import ingest_bytes, embed_pending
from paperlens.embeddings import Embedder

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["index","status","serve","user-add"])
    parser.add_argument("--data-dir",type=Path,default=ROOT/"data")
    parser.add_argument("--chunk-words",type=int,default=120)
    parser.add_argument("--overlap",type=int,default=25)
    parser.add_argument("--username")
    parser.add_argument("--role",choices=["admin","viewer"],default="viewer")
    parser.add_argument("--password-stdin",action="store_true")
    parser.add_argument("--auth",action="store_true",help="Require account login when serving")
    args=parser.parse_args()
    if args.command=="user-add":
        import getpass,sys
        from paperlens.auth import Auth
        if not args.username:parser.error("--username is required")
        password=sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("New password (12+ characters): ")
        if not args.password_stdin and password!=getpass.getpass("Confirm password: "):raise SystemExit("Passwords do not match.")
        print(json.dumps(Auth(Store(args.data_dir),True).create_user(args.username,password,args.role)))
        return
    if args.command=="serve":
        import uvicorn,os
        if args.auth:os.environ["PAPERLENS_AUTH_REQUIRED"]="1"
        uvicorn.run("paperlens.api:app",host="127.0.0.1",port=8765)
        return
    store=Store(args.data_dir)
    config_path=store.folder/"index-config.json"
    config={"chunk_words":args.chunk_words,"overlap_words":args.overlap}
    if args.command=="index":
        if config_path.exists() and json.loads(config_path.read_text())!=config:
            raise SystemExit("Chunk configuration changed. Use a fresh --data-dir for an experiment.")
        if args.chunk_words<20 or not 0<=args.overlap<args.chunk_words:
            raise SystemExit("Invalid chunk/overlap size.")
        config_path.write_text(json.dumps(config,indent=2),encoding="utf-8")
    if args.command=="index":
        manifest=ROOT/"data"/"papers"/"manifest.json"
        if manifest.exists():
            for p in json.loads(manifest.read_text(encoding="utf-8")):
                result=ingest_bytes(store,(manifest.parent/p["file"]).read_bytes(),p["title"],p["source_url"],p["status"],args.chunk_words,args.overlap)
                print("Corpus:",p["arxiv_id"],"duplicate" if result["duplicate"] else "imported",flush=True)
        embedder=Embedder(ROOT/".cache"/"embeddings")
        print("Embedded chunks:",embed_pending(store,embedder),flush=True)
    print(json.dumps(store.documents(),indent=2,ensure_ascii=True))

if __name__=="__main__": main()
