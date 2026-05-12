"""Shared helpers for helpdesk API tools."""
import base64
import json
import os
from typing import Any, Dict, Optional

import requests

TIMEOUT = int(os.getenv("AXSUPPORT_HTTP_TIMEOUT", "30"))


def env_status(required: list[str]) -> dict:
    return {key: bool(os.getenv(key)) for key in required}


def missing(required: list[str]) -> list[str]:
    return [key for key in required if not os.getenv(key)]


def response_payload(resp: requests.Response) -> Dict[str, Any]:
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:2000]
    return {"status_code": resp.status_code, "ok": resp.ok, "body": body}


def safe_request(method: str, url: str, *, headers: Optional[dict] = None, auth=None, params=None, json_body=None) -> dict:
    try:
        resp = requests.request(method, url, headers=headers, auth=auth, params=params, json=json_body, timeout=TIMEOUT)
        return response_payload(resp)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status_code": None}


def basic_auth_header(username: str, token: str) -> dict:
    raw = f"{username}:{token}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def dry_run_guard(execute: bool, payload: dict) -> dict:
    if not execute:
        return {"ok": True, "dry_run": True, "would_send": payload}
    return {"ok": True, "dry_run": False}
