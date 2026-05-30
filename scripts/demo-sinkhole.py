#!/usr/bin/env python3
"""
Local HTTP sinkhole for Pulsaride-H7 demos.

Strictly loopback-only (127.0.0.1 / localhost / ::1), returns 200 to any
method/path, writes NDJSON events without logging request body plaintext.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import IO


def make_handler(log_fp: IO[str]) -> type[BaseHTTPRequestHandler]:
    class SinkholeHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return b""
            length = min(length, 64 * 1024)
            return self.rfile.read(length)

        def _emit(self, body: bytes) -> None:
            event = {
                "event": "H7_SINKHOLE_HIT",
                "ts": time.time(),
                "client": self.client_address[0],
                "method": self.command,
                "path": self.path,
                "ua": self.headers.get("User-Agent", ""),
                "len": len(body),
                "body_sha256_first8": (
                    __import__("hashlib").sha256(body).hexdigest()[:8] if body else ""
                ),
            }
            line = json.dumps(event, ensure_ascii=False)
            print(line, flush=True)
            log_fp.write(line + "\n")
            log_fp.flush()

        def _respond(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Sinkhole", "pulsaride-h7-demo")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"sinkhole":true}\n')

        def do_GET(self) -> None:  # noqa: N802
            self._emit(b"")
            self._respond()

        def do_POST(self) -> None:  # noqa: N802
            body = self._read_body()
            self._emit(body)
            self._respond()

        def do_PUT(self) -> None:  # noqa: N802
            body = self._read_body()
            self._emit(body)
            self._respond()

    return SinkholeHandler


def main() -> int:
    p = argparse.ArgumentParser(description="Local sinkhole for H7 demos")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9999)
    p.add_argument("--log", default="/tmp/h7-sinkhole.ndjson")
    args = p.parse_args()

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        print(
            f"[sinkhole] REFUS: --host must be loopback (got {args.host!r})",
            file=sys.stderr,
        )
        return 2

    log_fp = open(args.log, "a", encoding="utf-8")  # noqa: SIM115
    handler = make_handler(log_fp)
    srv = HTTPServer((args.host, args.port), handler)
    print(
        f"[sinkhole] up on http://{args.host}:{args.port} (log -> {args.log})",
        file=sys.stderr,
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[sinkhole] stop", file=sys.stderr)
    finally:
        srv.server_close()
        log_fp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())