#!/usr/bin/env python3
"""Jira Service Management tool: request/issue search/read/update and triage."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage
REQUIRED=["JIRA_BASE_URL","JIRA_EMAIL","JIRA_API_TOKEN"]
def auth(): return (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
def base(): return os.getenv("JIRA_BASE_URL","").rstrip("/")
def run(args):
    action=args[0] if args else "check"
    if action=="check": return {"tool":"jira_service","ok":not missing(REQUIRED),"configured":env_status(REQUIRED),"missing":missing(REQUIRED)}
    if missing(REQUIRED): return {"tool":"jira_service","ok":False,"error":"Missing env vars","missing":missing(REQUIRED)}
    if action=="search":
        jql=" ".join(args[1:]) or f"project={os.getenv('JIRA_SERVICE_PROJECT_KEY','SUP')} ORDER BY created DESC"
        return {"tool":"jira_service","action":action,**safe_request("GET",base()+"/rest/api/3/search",auth=auth(),params={"jql":jql,"maxResults":25})}
    if action=="issue": return {"tool":"jira_service","action":action,**safe_request("GET",base()+f"/rest/api/3/issue/{args[1]}",auth=auth())}
    if action=="triage": return {"tool":"jira_service","action":action,**support_triage.run(["triage"," ".join(args[1:])])}
    if action=="comment":
        execute="--execute" in args; clean=[a for a in args[1:] if a!="--execute"]; key=clean[0]; body=" ".join(clean[1:])
        payload={"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":body}]}]}}
        guard=dry_run_guard(execute,payload)
        if guard.get("dry_run"): return {"tool":"jira_service","issue":key,**guard}
        return {"tool":"jira_service","action":action,**safe_request("POST",base()+f"/rest/api/3/issue/{key}/comment",auth=auth(),json_body=payload)}
    return {"tool":"jira_service","ok":False,"error":f"Unknown action {action}"}
if __name__=="__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
