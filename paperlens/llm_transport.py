"""Server-configured local model transport; never expose its access key to UI."""
import json
import os
from pathlib import Path
import urllib.request
from .answer import GenerationError
ROOT=Path(__file__).resolve().parents[1]

def local_request(payload,on_delta=None):
    endpoint=os.environ.get("PAPERLENS_LLM_BASE_URL","http://127.0.0.1:8766").rstrip("/")+"/v1/chat/completions"
    key_path=Path(os.environ.get("PAPERLENS_LLM_KEY_FILE",str(ROOT/".cache"/"local-llm"/"api-key.txt")))
    headers={"Content-Type":"application/json"}
    if key_path.exists():headers["Authorization"]="Bearer "+key_path.read_text(encoding="ascii").strip()
    if on_delta:
        payload={**payload,"stream":True,"stream_options":{"include_usage":True}}
    request=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=120) as response:
            if on_delta:
                content=[];usage={};finish=None;size=0
                while True:
                    line=response.readline(100001)
                    if not line:break
                    size+=len(line)
                    if len(line)>100000 or size>500000:raise GenerationError("Local model stream exceeded its limit.")
                    if not line.startswith(b"data:"):continue
                    value=line[5:].strip()
                    if value==b"[DONE]":break
                    event=json.loads(value)
                    if event.get("usage"):usage=event["usage"]
                    for choice in event.get("choices",[]):
                        if choice.get("finish_reason"):finish=choice["finish_reason"]
                        delta=choice.get("delta",{}).get("content") or ""
                        if delta:content.append(delta);on_delta(delta)
                if finish=="length":raise GenerationError("Local model reached its output limit.")
                if finish is None:raise GenerationError("Local model stream ended before completion.")
                return {"choices":[{"finish_reason":finish,"message":{"content":"".join(content)}}],"usage":usage}
            raw=response.read(500_001)
        if len(raw)>500_000:raise GenerationError("Local model response too large.")
        data=json.loads(raw)
        if data["choices"][0].get("finish_reason")=="length":
            if os.environ.get("PAPERLENS_DEBUG_MODEL")=="1":
                message=data["choices"][0].get("message",{})
                debug={"finish_reason":"length","usage":data.get("usage"),"tool_calls":message.get("tool_calls"),"content_tail":str(message.get("content") or "")[-500:]}
                (ROOT/"reports"/"model-output-limit.json").write_text(json.dumps(debug,indent=2),encoding="utf-8")
            raise GenerationError("Local model reached its output limit.")
        return data
    except GenerationError:raise
    except Exception as exc:raise GenerationError("Local model unavailable or returned invalid output. Check model service logs.") from exc
