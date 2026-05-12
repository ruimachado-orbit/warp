#!/usr/bin/env python3
"""Zendesk Support tool: ticket search/read/update, notes, macros, triage handoff."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from helpdesk_common import env_status, missing, safe_request, dry_run_guard
import support_triage

REQUIRED = ["ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN"]

def base_url(): return f"https://{os.getenv('ZENDESK_SUBDOMAIN')}.zendesk.com/api/v2"
def auth(): return (f"{os.getenv('ZENDESK_EMAIL')}/token", os.getenv("ZENDESK_API_TOKEN"))

def run(args):
    action = args[0] if args else "check"
    if action == "check":
        return {"tool":"zendesk", "ok": not missing(REQUIRED), "configured": env_status(REQUIRED), "missing": missing(REQUIRED)}
    miss = missing(REQUIRED)
    if miss:
        return {"tool":"zendesk", "ok": False, "error": "Missing required env vars", "missing": miss}
    if action == "search":
        query = " ".join(args[1:]) or "type:ticket status<solved"
        return {"tool":"zendesk", "action":action, **safe_request("GET", base_url()+"/search.json", auth=auth(), params={"query": query})}
    if action == "ticket":
        tid = args[1]
        return {"tool":"zendesk", "action":action, **safe_request("GET", base_url()+f"/tickets/{tid}.json", auth=auth())}
    if action == "triage":
        text = " ".join(args[1:])
        return {"tool":"zendesk", "action":action, **support_triage.run(["triage", text])}
    if action in {"update", "note", "reply"}:
        execute = "--execute" in args
        clean = [a for a in args[1:] if a != "--execute"]
        tid = clean[0]
        body = " ".join(clean[1:])
        payload = {"ticket": {}}
        if action == "note": payload["ticket"]["comment"] = {"body": body, "public": False}
        elif action == "reply": payload["ticket"]["comment"] = {"body": body, "public": True}
        else: payload["ticket"].update(json.loads(body) if body.strip().startswith("{") else {"additional_tags": body.split()})
        guard = dry_run_guard(execute, payload)
        if guard.get("dry_run"): return {"tool":"zendesk", "ticket_id": tid, **guard}
        return {"tool":"zendesk", "action":action, **safe_request("PUT", base_url()+f"/tickets/{tid}.json", auth=auth(), json_body=payload)}
    return {"tool":"zendesk", "ok":False, "error":f"Unknown action {action}", "actions":["check","search","ticket","triage","update","note","reply"]}
if __name__ == "__main__": print(json.dumps(run(sys.argv[1:]), indent=2, ensure_ascii=False))
