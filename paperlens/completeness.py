"""Conservative structural enumeration checks; not semantic correctness."""
import re
NUMBERS={"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12}
def requested_count(query):
    query=query.rsplit("Follow-up:",1)[-1]
    if not re.search(r"\b(what|which|list|name|identify|enumerate)\b",query,re.I):return None
    match=re.search(r"\b("+ "|".join(NUMBERS)+r"|[1-9]|1[0-2])\b",query,re.I)
    return NUMBERS.get(match[0].lower(),int(match[0]) if match and match[0].isdigit() else None) if match else None
def check(query,paragraphs):
    expected=requested_count(query)
    if expected is None:return {"passed":True,"requested_items":None,"scope":"No explicit numbered list requested."}
    text=" ".join(p["text"] for p in paragraphs).casefold()
    items=[re.sub(r"\s+"," ",item).strip().casefold() for p in paragraphs for item in p.get("items",[]) if isinstance(item,str)]
    distinct=set(items)
    passed=len(distinct)==expected and all(len(s)>2 and s in text for s in distinct)
    return {"passed":passed,"requested_items":expected,"distinct_items":len(distinct),"scope":"Explicit item count, distinct names and presence in answer text; not proof of completeness in meaning."}
