#!/usr/bin/env python3
"""Freshdesk tool: ticket listing/search/read/update and triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["FRESHDESK_DOMAIN","FRESHDESK_API_KEY"]
def base(): return f"https://{os.getenv('FRESHDESK_DOMAIN')}.freshdesk.com/api/v2"
def auth(): return (os.getenv("FRESHDESK_API_KEY"), "X")
def run(args):
    action=args[0] if args else "check"
    if action=="check": return {"tool":"freshdesk","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"freshdesk","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="tickets": return {"tool":"freshdesk","action":action,**safe_request("GET",base()+"/tickets",auth=auth(),params={"per_page":30})}
    if action=="ticket": return {"tool":"freshdesk","action":action,**safe_request("GET",base()+f"/tickets/{args[1]}",auth=auth())}
    if action=="search": return {"tool":"freshdesk","action":action,**safe_request("GET",base()+"/search/tickets",auth=auth(),params={"query":" ".join(args[1:])})}
    if action=="triage": return {"tool":"freshdesk","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action in {"note","reply"}:
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; tid=clean[0]; body=" ".join(clean[1:])
        endpoint="notes" if action=="note" else "reply"; payload={"body":body, "private": action=="note"}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"freshdesk","ticket_id":tid,**guard}
        return {"tool":"freshdesk","action":action,**safe_request("POST",base()+f"/tickets/{tid}/{endpoint}",auth=auth(),json_body=payload)}
    return {"tool":"freshdesk","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
