#!/usr/bin/env python3
"""Security regression tests for the h7-monitor FastAPI gateway.

Validates:
- GET /qr/{filename} rejects path-traversal and absolute-path payloads.
- WebSocket /stream never leaks stack traces or raw exception bodies.
- CORS: wildcard origin (*) is never reflected; only allow-listed origins accepted.

The monitor backend lives in a sibling repository. Point H7_MONITOR_BACKEND_DIR
to the absolute path of its `backend/` directory (default: ../../h7-monitor/backend).

Exit code 0 on success, 1 on any regression. No external pytest dependency.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

DEFAULT_BACKEND = Path(__file__).resolve().parent.parent.parent.parent / "h7-monitor" / "backend"
BACKEND_DIR = Path(os.environ.get("H7_MONITOR_BACKEND_DIR", str(DEFAULT_BACKEND))).resolve()


def _load_app():
    if not BACKEND_DIR.is_dir():
        raise SystemExit(f"[gate-test] backend dir not found: {BACKEND_DIR} "
                         f"(set H7_MONITOR_BACKEND_DIR)")
    sys.path.insert(0, str(BACKEND_DIR))
    try:
        from main import app  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - import failure path
        raise SystemExit(f"[gate-test] cannot import monitor backend `main:app`: {exc}")
    return app


def _new_client():
    try:
        from fastapi.testclient import TestClient  # type: ignore
    except Exception as exc:
        raise SystemExit(f"[gate-test] fastapi.testclient unavailable: {exc}. "
                         "Install: pip install 'fastapi[testclient]' httpx")
    return TestClient(_load_app())


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TRAVERSAL_PATHS = [
    "../../etc/passwd",
    "../../etc/passwd.png",
    "..%2F..%2Fetc%2Fpasswd.png",
    "/etc/passwd",
    "/etc/passwd.png",
    "..\\..\\windows\\win.ini",
    "sub/dir.png",
    ".hidden.png",
    "..",
]


def test_qr_rejects_traversal(client) -> list[str]:
    failures: list[str] = []
    for payload in TRAVERSAL_PATHS:
        resp = client.get(f"/qr/{payload}")
        # Acceptable refusals: 400 (filename guard), 404 (not found), 422 (route guard).
        if resp.status_code not in (400, 404, 422):
            failures.append(
                f"  /qr/{payload!r} -> HTTP {resp.status_code} (expected 400/404/422)"
            )
            continue
        body = resp.text.lower()
        if "/etc/passwd" in body or "win.ini" in body or "traceback" in body:
            failures.append(f"  /qr/{payload!r} body leaks payload or trace: {body[:120]!r}")
    return failures


def test_cors_no_wildcard(client) -> list[str]:
    """CORS must never reflect * or an untrusted origin."""
    failures: list[str] = []

    # A rogue origin that should never be echoed back.
    rogue_origin = "https://evil.example.com"
    resp = client.get("/health", headers={"Origin": rogue_origin})
    acao = resp.headers.get("access-control-allow-origins") or resp.headers.get("access-control-allow-origin", "")
    if acao == "*":
        failures.append(f"  /health reflects wildcard ACAO for rogue origin")
    if rogue_origin in acao:
        failures.append(f"  /health echoes untrusted origin {rogue_origin!r} in ACAO: {acao!r}")

    # Preflight from rogue origin: must not grant access.
    pre = client.options(
        "/attest/test",
        headers={
            "Origin": rogue_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    acao_pre = pre.headers.get("access-control-allow-origins") or pre.headers.get("access-control-allow-origin", "")
    if acao_pre == "*":
        failures.append(f"  OPTIONS /attest reflects wildcard ACAO")
    if rogue_origin in acao_pre:
        failures.append(f"  OPTIONS /attest echoes untrusted origin in ACAO: {acao_pre!r}")

    return failures


def test_stream_hides_traces(client) -> list[str]:
    failures: list[str] = []
    try:
        with client.websocket_connect("/stream") as ws:
            # Force a server-side fault by sending a binary blob the handler
            # does not expect to surface to clients. The contract is: either
            # the connection closes cleanly, or it returns a sanitized JSON
            # envelope. It must never return Python traceback text.
            try:
                ws.send_bytes(b"\x00\x01\x02malicious")
                ws.send_text("ping")
            except Exception:
                pass

            try:
                msg = ws.receive_text(timeout=1.0) if hasattr(ws, "receive_text") else None
            except Exception:
                msg = None

            if msg:
                lower = msg.lower()
                if "traceback" in lower or 'file "' in lower or "exception" in lower:
                    failures.append(f"  /stream leaks trace: {msg[:160]!r}")
                else:
                    try:
                        payload = json.loads(msg)
                        if not isinstance(payload, dict):
                            failures.append(f"  /stream non-object payload: {msg[:160]!r}")
                    except json.JSONDecodeError:
                        failures.append(f"  /stream non-JSON payload: {msg[:160]!r}")
    except Exception as exc:
        # Connection-level failure is acceptable as long as no trace leaked.
        if "traceback" in str(exc).lower():
            failures.append(f"  /stream raised trace-bearing error: {exc!r}")
    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    client = _new_client()

    total = 0
    failed = 0

    cases = [
        ("/qr path-traversal hardening", test_qr_rejects_traversal),
        ("/stream trace concealment", test_stream_hides_traces),
        ("CORS no-wildcard / no rogue origin echo", test_cors_no_wildcard),
    ]

    for name, fn in cases:
        total += 1
        try:
            issues = fn(client)
        except Exception:
            failed += 1
            print(f"[FAIL] {name}\n{traceback.format_exc()}")
            continue
        if issues:
            failed += 1
            print(f"[FAIL] {name}")
            for issue in issues:
                print(issue)
        else:
            print(f"[ OK ] {name}")

    print(f"[gate-test] {total - failed}/{total} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
