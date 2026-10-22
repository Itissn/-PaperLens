"""SSE helpers and provisional text extraction. Drafts are never verified answers."""
import json,re
def draft_text(raw):
    parts=[]
    for match in re.finditer(r'"(?:text|name)"\s*:\s*"((?:[^"\\]|\\.)*)',raw):
        value=match[1]
        for trim in range(min(8,len(value))+1):
            try:
                parts.append(json.loads('"'+(value[:-trim] if trim else value)+'"'));break
            except (ValueError,UnicodeError):continue
    return "\n\n".join(parts)
def encode_event(event,data):
    return "event: "+event+"\ndata: "+json.dumps(data,ensure_ascii=False)+"\n\n"
