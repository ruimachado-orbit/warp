#!/usr/bin/env python3
"""Local knowledge-base search and answer support."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
KB_DIR = ROOT / "knowledge"

def search(query: str):
    terms=[t.lower() for t in query.split() if len(t)>2]
    results=[]
    if not KB_DIR.exists(): return []
    for path in list(KB_DIR.rglob("*.md")) + list(KB_DIR.rglob("*.txt")):
        text=path.read_text(errors="ignore")
        lower=text.lower(); score=sum(lower.count(t) for t in terms)
        if score:
            idx=min([lower.find(t) for t in terms if t in lower] or [0])
            excerpt=text[max(0,idx-160):idx+500].replace("\n"," ")
            results.append({"path":str(path.relative_to(ROOT)),"score":score,"excerpt":excerpt})
    return sorted(results, key=lambda r:r["score"], reverse=True)[:10]

def run(args):
    action=args[0] if args else "search"; query=" ".join(args[1:] if len(args)>1 else args)
    return {"tool":"knowledge_base","ok":True,"action":action,"query":query,"results":search(query)}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
