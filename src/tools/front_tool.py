#!/usr/bin/env python3
"""Front tool: inbox conversations, comments, replies, and triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["FRONT_API_TOKEN"]
def headers(): return {"Authorization":f"Bearer {os.getenv('FRONT_API_TOKEN')}","Content-Type":"application/json"}
def run(args):
    action=args[0] if args else "check"; base="https://api2.frontapp.com"
    if action=="check": return {"tool":"front","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"front","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="conversations": return {"tool":"front","action":action,**safe_request("GET",base+"/conversations",headers=headers(),params={"limit":25})}
    if action=="conversation": return {"tool":"front","action":action,**safe_request("GET",base+f"/conversations/{args[1]}",headers=headers())}
    if action=="triage": return {"tool":"front","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action in {"comment","reply"}:
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; cid=clean[0]; body=" ".join(clean[1:])
        endpoint="comments" if action=="comment" else "messages"; payload={"body":body}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"front","conversation_id":cid,**guard}
        return {"tool":"front","action":action,**safe_request("POST",base+f"/conversations/{cid}/{endpoint}",headers=headers(),json_body=payload)}
    return {"tool":"front","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
