#!/usr/bin/env python3
"""Salesforce Service Cloud tool: Cases search/read/update and triage."""
import json, os, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["SALESFORCE_INSTANCE_URL","SALESFORCE_ACCESS_TOKEN"]
def headers(): return {"Authorization":f"Bearer {os.getenv('SALESFORCE_ACCESS_TOKEN')}","Content-Type":"application/json"}
def base(): return os.getenv("SALESFORCE_INSTANCE_URL","").rstrip("/")+"/services/data/v60.0"
def run(args):
    action=args[0] if args else "check"
    if action=="check": return {"tool":"salesforce_service","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"salesforce_service","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="cases":
        q="SELECT Id,CaseNumber,Subject,Status,Priority,Origin,CreatedDate FROM Case ORDER BY CreatedDate DESC LIMIT 25"
        return {"tool":"salesforce_service","action":action,**safe_request("GET",base()+"/query",headers=headers(),params={"q":q})}
    if action=="case": return {"tool":"salesforce_service","action":action,**safe_request("GET",base()+f"/sobjects/Case/{args[1]}",headers=headers())}
    if action=="triage": return {"tool":"salesforce_service","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action=="update":
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; cid=clean[0]; payload=json.loads(" ".join(clean[1:]))
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"salesforce_service","case_id":cid,**guard}
        return {"tool":"salesforce_service","action":action,**safe_request("PATCH",base()+f"/sobjects/Case/{cid}",headers=headers(),json_body=payload)}
    return {"tool":"salesforce_service","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
