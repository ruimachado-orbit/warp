     1|#!/usr/bin/env python3
     2|"""Warp — Customer Support Operations Orchestrator."""
     3|import json
     4|import subprocess
     5|import sys
     6|import time
     7|from pathlib import Path
     8|
     9|SCRIPT_DIR = Path(__file__).parent
    10|sys.path.insert(0, str(SCRIPT_DIR))
    11|
    12|from config import get
    13|from llm_gateway import call_with_fallback, status as llm_status
    14|
    15|TOOLS_DIR = SCRIPT_DIR / "tools"
    16|SYSTEM_PROMPT_PATH = SCRIPT_DIR.parent / "prompts" / "system-prompt.md"
    17|
    18|TOOLS = {
    19|    "support_triage": {"script": "support_triage.py", "purpose": "Classify ticket category/severity/sentiment, route queue, SLA, tags, and draft first reply."},
    20|    "knowledge": {"script": "knowledge_tool.py", "purpose": "Search local support knowledge base, macros, policies, and troubleshooting docs."},
    21|    "zendesk": {"script": "zendesk_tool.py", "purpose": "Zendesk Support tickets: search/read/update, notes, replies."},
    22|    "intercom": {"script": "intercom_tool.py", "purpose": "Intercom conversations: list/read, notes, replies."},
    23|    "freshdesk": {"script": "freshdesk_tool.py", "purpose": "Freshdesk tickets: list/search/read/update, notes, replies."},
    24|    "salesforce_service": {"script": "salesforce_service_tool.py", "purpose": "Salesforce Service Cloud Cases: query/read/update."},
    25|    "hubspot_service": {"script": "hubspot_service_tool.py", "purpose": "HubSpot Service Hub tickets: list/read/update."},
    26|    "jira_service": {"script": "jira_service_tool.py", "purpose": "Jira Service Management issues/requests: search/read/comment."},
    27|    "front": {"script": "front_tool.py", "purpose": "Front conversations: list/read/comment/reply."},
    28|    "helpscout": {"script": "helpscout_tool.py", "purpose": "Help Scout conversations: list/read/note/reply."},
    29|    "slack": {"script": "slack_tool.py", "purpose": "Slack collaboration/escalation notifications."},
    30|    "notion": {"script": "notion_tool.py", "purpose": "Notion knowledge/product docs integration."},
    31|}
    32|
    33|HELPDESK_KEYWORDS = {
    34|    "zendesk": ["zendesk", "zd"],
    35|    "intercom": ["intercom"],
    36|    "freshdesk": ["freshdesk"],
    37|    "salesforce_service": ["salesforce", "service cloud", "case"],
    38|    "hubspot_service": ["hubspot", "service hub"],
    39|    "jira_service": ["jira", "jsm", "service management"],
    40|    "front": ["front", "frontapp"],
    41|    "helpscout": ["help scout", "helpscout"],
    42|}
    43|
    44|TRIAGE_KEYWORDS = ["triage", "classify", "classification", "priority", "severity", "route", "sla", "tag", "categorize", "draft", "reply", "customer", "ticket", "conversation", "case", "request", "issue"]
    45|KB_KEYWORDS = ["knowledge", "kb", "faq", "macro", "runbook", "policy", "troubleshoot", "answer"]
    46|
    47|
    48|def load_system_prompt() -> str:
    49|    try:
    50|        return SYSTEM_PROMPT_PATH.read_text().strip()
    51|    except Exception:
    52|        return "You are Warp, a customer support operations agent. Be precise, safe, and customer-centric."
    53|
    54|
    55|def analyze_context(goal: str) -> list[str]:
    56|    lower = goal.lower()
    57|    selected = []
    58|    if any(k in lower for k in TRIAGE_KEYWORDS):
    59|        selected.append("support_triage")
    60|    if any(k in lower for k in KB_KEYWORDS):
    61|        selected.append("knowledge")
    62|    for tool, keywords in HELPDESK_KEYWORDS.items():
    63|        if any(k in lower for k in keywords):
    64|            selected.append(tool)
    65|    if any(k in lower for k in ["escalate", "notify", "slack", "channel"]):
    66|        selected.append("slack")
    67|    if any(k in lower for k in ["notion", "docs"]):
    68|        selected.append("notion")
    69|    if not selected:
    70|        selected = ["support_triage", "knowledge"]
    71|    # preserve order, dedupe
    72|    out=[]
    73|    for item in selected:
    74|        if item not in out and item in TOOLS:
    75|            out.append(item)
    76|    return out
    77|
    78|
    79|def _tool_args(tool_name: str, goal: str) -> list[str]:
    80|    lower = goal.lower()
    81|    if tool_name == "support_triage":
    82|        return ["triage", goal]
    83|    if tool_name == "knowledge":
    84|        return ["search", goal]
    85|    # Safe default for external systems: check config unless explicit action named.
    86|    if any(word in lower for word in ["search", "find", "list", "open", "get"]):
    87|        if tool_name in {"zendesk", "freshdesk", "jira_service"}:
    88|            return ["search", goal]
    89|        if tool_name in {"intercom", "front", "helpscout"}:
    90|            return ["conversations"]
    91|        if tool_name in {"salesforce_service"}:
    92|            return ["cases"]
    93|        if tool_name in {"hubspot_service"}:
    94|            return ["tickets"]
    95|    return ["check"]
    96|
    97|
    98|def run_tool(tool_name: str, goal: str, quiet: bool = False) -> dict:
    99|    if tool_name not in TOOLS:
   100|        return {"tool": tool_name, "ok": False, "error": f"Unknown tool: {tool_name}"}
   101|    script_path = TOOLS_DIR / TOOLS[tool_name]["script"]
   102|    args = _tool_args(tool_name, goal)
   103|    if not quiet:
   104|        print(f"  🔍 Running {tool_name}: {TOOLS[tool_name]['purpose']}")
   105|    start = time.time()
   106|    try:
   107|        result = subprocess.run([sys.executable, str(script_path), *args], capture_output=True, text=True, timeout=90)
   108|        elapsed = round(time.time() - start, 2)
   109|        if result.returncode != 0:
   110|            return {"tool": tool_name, "ok": False, "error": result.stderr.strip(), "_execution_time": elapsed}
   111|        try:
   112|            payload = json.loads(result.stdout)
   113|        except Exception:
   114|            payload = {"tool": tool_name, "ok": True, "raw": result.stdout}
   115|        payload["_execution_time"] = elapsed
   116|        return payload
   117|    except Exception as exc:
   118|        return {"tool": tool_name, "ok": False, "error": str(exc), "_execution_time": round(time.time() - start, 2)}
   119|
   120|
   121|def _format_tool_results(results: list[dict]) -> str:
   122|    return json.dumps(results, indent=2, ensure_ascii=False)[:12000]
   123|
   124|
   125|def llm_synthesize(goal: str, tool_results: list[dict], provider: str | None = None, quiet: bool = False) -> str:
   126|    system = load_system_prompt()
   127|    prompt = f"""Customer support goal/request:\n{goal}\n\nTool results:\n{_format_tool_results(tool_results)}\n\nReturn a concise operations-ready answer with: classification, queue/owner, SLA, recommended next action, draft customer reply if relevant, and any missing information. Never claim an external update was made unless a tool result proves it. If a tool is not configured, say what env vars are missing."""
   128|    providers = get("llm.providers", ["anthropic", "openai", "openrouter"])
   129|    if provider:
   130|        providers = [provider] + [p for p in providers if p != provider]
   131|    if not quiet:
   132|        print("\n🤖 Synthesizing support plan...")
   133|    result = call_with_fallback(prompt, providers=providers, system=system, max_tokens=get("llm.max_tokens", 4096), temperature=get("llm.temperature", 0.2))
   134|    if result.get("ok"):
   135|        if not quiet:
   136|            print(f"   ✓ Using {result.get('provider')}/{result.get('model')}")
   137|        return result["text"]
   138|    return _synthesize_logic(tool_results)
   139|
   140|
   141|def _synthesize_logic(results: list[dict]) -> str:
   142|    triage = next((r for r in results if r.get("tool") in {"support_triage", "zendesk", "intercom", "freshdesk", "salesforce_service", "hubspot_service", "jira_service", "front", "helpscout"} and r.get("classification")), None)
   143|    if not triage:
   144|        return json.dumps(results, indent=2, ensure_ascii=False)[:4000]
   145|    c = triage["classification"]
   146|    lines = [
   147|        f"Classification: {c['category']} / {c['severity']} / {c['sentiment']}",
   148|        f"Route: {c['route_to']}",
   149|        f"SLA: {c['sla_hours']}h",
   150|        f"Tags: {', '.join(c['tags'])}",
   151|        f"Human required: {c['requires_human']}",
   152|    ]
   153|    if triage.get("draft_reply"):
   154|        lines.extend(["", "Draft reply:", triage["draft_reply"]])
   155|    return "\n".join(lines)
   156|
   157|
   158|def orchestrate(goal: str, use_llm: bool = True, provider: str | None = None, quiet: bool = False) -> str:
   159|    if not quiet:
   160|        print(f"🎧 Warp: {goal}")
   161|    tools = analyze_context(goal)
   162|    if not quiet:
   163|        print(f"🛠️  Tools: {tools}")
   164|    results = [run_tool(tool, goal, quiet=quiet) for tool in tools]
   165|    return llm_synthesize(goal, results, provider=provider, quiet=quiet) if use_llm else _synthesize_logic(results)
   166|
   167|
   168|if __name__ == "__main__":
   169|    use_llm = "--no-llm" not in sys.argv
   170|    if "--status" in sys.argv or "-s" in sys.argv:
   171|        print(json.dumps(llm_status(), indent=2))
   172|        sys.exit(0)
   173|    provider = None
   174|    if "--provider" in sys.argv:
   175|        idx = sys.argv.index("--provider")
   176|        if idx + 1 < len(sys.argv):
   177|            provider = sys.argv[idx + 1]
   178|    args = [a for a in sys.argv[1:] if a not in {"--no-llm", "--status", "-s", "--provider", provider}]
   179|    goal = " ".join(args) if args else "triage this ticket"
   180|    print("\n" + orchestrate(goal, use_llm=use_llm, provider=provider))
   181|