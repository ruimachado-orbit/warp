#!/usr/bin/env python3
"""Intercom tool: conversations, contacts, notes, assignment-ready triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["INTERCOM_ACCESS_TOKEN"]
def headers(): return {"Authorization": f"Bearer {os.getenv('INTERCOM_ACCESS_TOKEN')}", "Accept":"application/json", "Content-Type":"application/json", "Intercom-Version":"2.11"}
def run(args):
    action=args[0] if args else "check"
    if action=="check": return {"tool":"intercom","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"intercom","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    base="https://api.intercom.io"
    if action=="conversations": return {"tool":"intercom","action":action,**safe_request("GET",base+"/conversations",headers=headers(),params={"per_page":20})}
    if action=="conversation": return {"tool":"intercom","action":action,**safe_request("GET",base+f"/conversations/{args[1]}",headers=headers())}
    if action=="triage": return {"tool":"intercom","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action in {"note","reply"}:
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; cid=clean[0]; body=" ".join(clean[1:])
        payload={"message_type":"comment","type":"admin","body":body}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"intercom","conversation_id":cid,**guard}
        return {"tool":"intercom","action":action,**safe_request("POST",base+f"/conversations/{cid}/reply",headers=headers(),json_body=payload)}
    return {"tool":"intercom","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
