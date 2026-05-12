#!/usr/bin/env python3
"""HubSpot Service Hub tool: CRM tickets list/read/update and triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["HUBSPOT_ACCESS_TOKEN"]
def headers(): return {"Authorization":f"Bearer {os.getenv('HUBSPOT_ACCESS_TOKEN')}","Content-Type":"application/json"}
def run(args):
    action=args[0] if args else "check"; base="https://api.hubapi.com"
    if action=="check": return {"tool":"hubspot_service","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"hubspot_service","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="tickets": return {"tool":"hubspot_service","action":action,**safe_request("GET",base+"/crm/v3/objects/tickets",headers=headers(),params={"limit":50,"properties":"subject,content,hs_pipeline_stage,hs_ticket_priority,createdate"})}
    if action=="ticket": return {"tool":"hubspot_service","action":action,**safe_request("GET",base+f"/crm/v3/objects/tickets/{args[1]}",headers=headers(),params={"properties":"subject,content,hs_pipeline_stage,hs_ticket_priority"})}
    if action=="triage": return {"tool":"hubspot_service","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action=="update":
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; tid=clean[0]; payload={"properties":json.loads(" ".join(clean[1:]))}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"hubspot_service","ticket_id":tid,**guard}
        return {"tool":"hubspot_service","action":action,**safe_request("PATCH",base+f"/crm/v3/objects/tickets/{tid}",headers=headers(),json_body=payload)}
    return {"tool":"hubspot_service","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
