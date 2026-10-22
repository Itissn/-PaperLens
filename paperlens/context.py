"""Page-local context stitching for second-stage reading, with explicit provenance."""
def page_window(rows,anchor,max_words=240):
    current=rows[anchor]
    neighbors=sorted([r for r in rows if r["document_id"]==current["document_id"] and r["page"]==current["page"] and abs(r["position"]-current["position"])<=1],key=lambda r:r["position"])
    words=[];start=0
    for row in neighbors:
        part=row["text"].split()
        overlap=0
        for size in range(min(60,len(words),len(part)),0,-1):
            if words[-size:]==part[:size]:overlap=size;break
        offset=len(words)-overlap
        if row["id"]==current["id"]:start=offset
        words.extend(part[overlap:])
    center=start+len(current["text"].split())//2
    lower=max(0,min(center-max_words//2,len(words)-max_words))
    return " ".join(words[lower:lower+max_words]),[r["id"] for r in neighbors]
