#!/usr/bin/env python3
"""Warp — Customer Support Operations Orchestrator."""
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import get
from llm_gateway import call_with_fallback, status as llm_status

TOOLS_DIR = SCRIPT_DIR / "tools"
SYSTEM_PROMPT_PATH = SCRIPT_DIR.parent / "prompts" / "system-prompt.md"

TOOLS = {
    "support_triage": {"script": "support_triage.py", "purpose": "Classify ticket category/severity/sentiment, route queue, SLA, tags, and draft first reply."},
    "knowledge": {"script": "knowledge_tool.py", "purpose": "Search local support knowledge base, macros, policies, and troubleshooting docs."},
    "zendesk": {"script": "zendesk_tool.py", "purpose": "Zendesk Support tickets: search/read/update, notes, replies."},
    "intercom": {"script": "intercom_tool.py", "purpose": "Intercom conversations: list/read, notes, replies."},
    "freshdesk": {"script": "freshdesk_tool.py", "purpose": "Freshdesk tickets: list/search/read/update, notes, replies."},
    "salesforce_service": {"script": "salesforce_service_tool.py", "purpose": "Salesforce Service Cloud Cases: query/read/update."},
    "hubspot_service": {"script": "hubspot_service_tool.py", "purpose": "HubSpot Service Hub tickets: list/read/update."},
    "jira_service": {"script": "jira_service_tool.py", "purpose": "Jira Service Management issues/requests: search/read/comment."},
    "front": {"script": "front_tool.py", "purpose": "Front conversations: list/read/comment/reply."},
    "helpscout": {"script": "helpscout_tool.py", "purpose": "Help Scout conversations: list/read/note/reply."},
    "slack": {"script": "slack_tool.py", "purpose": "Slack collaboration/escalation notifications."},
    "notion": {"script": "notion_tool.py", "purpose": "Notion knowledge/product docs integration."},
}

HELPDESK_KEYWORDS = {
    "zendesk": ["zendesk", "zd"],
    "intercom": ["intercom"],
    "freshdesk": ["freshdesk"],
    "salesforce_service": ["salesforce", "service cloud", "case"],
    "hubspot_service": ["hubspot", "service hub"],
    "jira_service": ["jira", "jsm", "service management"],
    "front": ["front", "frontapp"],
    "helpscout": ["help scout", "helpscout"],
}

TRIAGE_KEYWORDS = ["triage", "classify", "classification", "priority", "severity", "route", "sla", "tag", "categorize", "draft", "reply", "customer", "ticket", "conversation", "case", "request", "issue"]
KB_KEYWORDS = ["knowledge", "kb", "faq", "macro", "runbook", "policy", "troubleshoot", "answer"]


def load_system_prompt() -> str:
    try:
        return SYSTEM_PROMPT_PATH.read_text().strip()
    except Exception:
        return "You are Warp, a customer support operations agent. Be precise, safe, and customer-centric."


def analyze_context(goal: str) -> list[str]:
    lower = goal.lower()
    selected = []
    if any(k in lower for k in TRIAGE_KEYWORDS):
        selected.append("support_triage")
    if any(k in lower for k in KB_KEYWORDS):
        selected.append("knowledge")
    for tool, keywords in HELPDESK_KEYWORDS.items():
        if any(k in lower for k in keywords):
            selected.append(tool)
    if any(k in lower for k in ["escalate", "notify", "slack", "channel"]):
        selected.append("slack")
    if any(k in lower for k in ["notion", "docs"]):
        selected.append("notion")
    if not selected:
        selected = ["support_triage", "knowledge"]
    # preserve order, dedupe
    out=[]
    for item in selected:
        if item not in out and item in TOOLS:
            out.append(item)
    return out


def _tool_args(tool_name: str, goal: str) -> list[str]:
    lower = goal.lower()
    if tool_name == "support_triage":
        return ["triage", goal]
    if tool_name == "knowledge":
        return ["search", goal]
    # Safe default for external systems: check config unless explicit action named.
    if any(word in lower for word in ["search", "find", "list", "open", "get"]):
        if tool_name in {"zendesk", "freshdesk", "jira_service"}:
            return ["search", goal]
        if tool_name in {"intercom", "front", "helpscout"}:
            return ["conversations"]
        if tool_name in {"salesforce_service"}:
            return ["cases"]
        if tool_name in {"hubspot_service"}:
            return ["tickets"]
    return ["check"]


def run_tool(tool_name: str, goal: str, quiet: bool = False) -> dict:
    if tool_name not in TOOLS:
        return {"tool": tool_name, "ok": False, "error": f"Unknown tool: {tool_name}"}
    script_path = TOOLS_DIR / TOOLS[tool_name]["script"]
    args = _tool_args(tool_name, goal)
    if not quiet:
        print(f"  🔍 Running {tool_name}: {TOOLS[tool_name]['purpose']}")
    start = time.time()
    try:
        result = subprocess.run([sys.executable, str(script_path), *args], capture_output=True, text=True, timeout=90)
        elapsed = round(time.time() - start, 2)
        if result.returncode != 0:
            return {"tool": tool_name, "ok": False, "error": result.stderr.strip(), "_execution_time": elapsed}
        try:
            payload = json.loads(result.stdout)
        except Exception:
            payload = {"tool": tool_name, "ok": True, "raw": result.stdout}
        payload["_execution_time"] = elapsed
        return payload
    except Exception as exc:
        return {"tool": tool_name, "ok": False, "error": str(exc), "_execution_time": round(time.time() - start, 2)}


def _format_tool_results(results: list[dict]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False)[:12000]


def llm_synthesize(goal: str, tool_results: list[dict], provider: str | None = None, quiet: bool = False) -> str:
    system = load_system_prompt()
    prompt = f"""Customer support goal/request:\n{goal}\n\nTool results:\n{_format_tool_results(tool_results)}\n\nReturn a concise operations-ready answer with: classification, queue/owner, SLA, recommended next action, draft customer reply if relevant, and any missing information. Never claim an external update was made unless a tool result proves it. If a tool is not configured, say what env vars are missing."""
    providers = get("llm.providers", ["anthropic", "openai", "openrouter", "codex_app_server"])
    if provider:
        providers = [provider] + [p for p in providers if p != provider]
    if not quiet:
        print("\n🤖 Synthesizing support plan...")
    result = call_with_fallback(prompt, providers=providers, system=system, max_tokens=get("llm.max_tokens", 4096), temperature=get("llm.temperature", 0.2))
    if result.get("ok"):
        if not quiet:
            print(f"   ✓ Using {result.get('provider')}/{result.get('model')}")
        return result["text"]
    return _synthesize_logic(tool_results)


def _synthesize_logic(results: list[dict]) -> str:
    triage = next((r for r in results if r.get("tool") in {"support_triage", "zendesk", "intercom", "freshdesk", "salesforce_service", "hubspot_service", "jira_service", "front", "helpscout"} and r.get("classification")), None)
    if not triage:
        return json.dumps(results, indent=2, ensure_ascii=False)[:4000]
    c = triage["classification"]
    lines = [
        f"Classification: {c['category']} / {c['severity']} / {c['sentiment']}",
        f"Route: {c['route_to']}",
        f"SLA: {c['sla_hours']}h",
        f"Tags: {', '.join(c['tags'])}",
        f"Human required: {c['requires_human']}",
    ]
    if triage.get("draft_reply"):
        lines.extend(["", "Draft reply:", triage["draft_reply"]])
    return "\n".join(lines)


def orchestrate(goal: str, use_llm: bool = True, provider: str | None = None, quiet: bool = False) -> str:
    if not quiet:
        print(f"🎧 Warp: {goal}")
    tools = analyze_context(goal)
    if not quiet:
        print(f"🛠️  Tools: {tools}")
    results = [run_tool(tool, goal, quiet=quiet) for tool in tools]
    return llm_synthesize(goal, results, provider=provider, quiet=quiet) if use_llm else _synthesize_logic(results)


if __name__ == "__main__":
    use_llm = "--no-llm" not in sys.argv
    if "--status" in sys.argv or "-s" in sys.argv:
        print(json.dumps(llm_status(), indent=2))
        sys.exit(0)
    provider = None
    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]
    args = [a for a in sys.argv[1:] if a not in {"--no-llm", "--status", "-s", "--provider", provider}]
    goal = " ".join(args) if args else "triage this ticket"
    print("\n" + orchestrate(goal, use_llm=use_llm, provider=provider))
