#!/usr/bin/env python3
"""Help Scout tool: conversations, notes/replies, and triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["HELPSCOUT_ACCESS_TOKEN"]
def headers(): return {"Authorization":f"Bearer {os.getenv('HELPSCOUT_ACCESS_TOKEN')}","Content-Type":"application/json"}
def run(args):
    action=args[0] if args else "check"; base="https://api.helpscout.net/v2"
    if action=="check": return {"tool":"helpscout","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"helpscout","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="conversations": return {"tool":"helpscout","action":action,**safe_request("GET",base+"/conversations",headers=headers(),params={"status":"active"})}
    if action=="conversation": return {"tool":"helpscout","action":action,**safe_request("GET",base+f"/conversations/{args[1]}",headers=headers())}
    if action=="triage": return {"tool":"helpscout","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action in {"note","reply"}:
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; cid=clean[0]; body=" ".join(clean[1:])
        payload={"text":body, "status":"active", "type":"note" if action=="note" else "reply"}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"helpscout","conversation_id":cid,**guard}
        return {"tool":"helpscout","action":action,**safe_request("POST",base+f"/conversations/{cid}/threads",headers=headers(),json_body=payload)}
    return {"tool":"helpscout","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
