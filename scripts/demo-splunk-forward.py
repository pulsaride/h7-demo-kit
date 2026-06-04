#!/usr/bin/env python3
"""Forward alerts.ndjson to Splunk HEC in real-time.

Usage:
    python3 scripts/demo-splunk-forward.py \\
        --ndjson  run/logs/alerts.ndjson \\
        --hec-url https://localhost:8098/services/collector/event \\
        --token   h7-demo-token-2026 \\
        --duration 60
"""
import argparse, json, ssl, sys, time, urllib.request

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ndjson",   default="run/logs/alerts.ndjson")
    p.add_argument("--hec-url",  default="https://localhost:8098/services/collector/event")
    p.add_argument("--token",    default="h7-demo-token-2026")
    p.add_argument("--duration", type=int, default=60)
    args = p.parse_args()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    print(f"[fwd] {args.ndjson} → {args.hec_url} (up to {args.duration}s)")
    sent = breach = 0
    deadline = time.time() + args.duration

    with open(args.ndjson) as f:
        f.seek(0, 2)   # tail: only new lines
        while time.time() < deadline:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "alert_cert_path" in d:
                d["cert_path"] = d.pop("alert_cert_path")

            payload = json.dumps({
                "time":       d.get("ts_ns", int(time.time() * 1e9)) / 1e9,
                "host":       d.get("host", "h7-demo"),
                "sourcetype": "pulsaride:h7:alert",
                "index":      "main",
                "event":      d,
            }).encode()
            req = urllib.request.Request(
                args.hec_url, data=payload,
                headers={"Authorization": f"Splunk {args.token}",
                         "Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, context=ctx, timeout=3).read()
                sent += 1
                if d.get("severity") == "CRITICAL":
                    breach += 1
                    print(f"  🔴 BREACH  tick={d.get('tick'):<4} kappa={d.get('kappa',0):.4f} → HEC OK")
                elif sent <= 3 or sent % 20 == 0:
                    print(f"  tick={d.get('tick'):<4} kappa={d.get('kappa',0):.4f} → OK")
            except Exception as e:
                print(f"  [ERR] {e}", file=sys.stderr)

    print(f"\n[fwd] done: {sent} events sent ({breach} BREACH) in {args.duration}s")

if __name__ == "__main__":
    main()
