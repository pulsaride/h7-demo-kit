#!/usr/bin/env python3
"""Génère run/h7-demo.toml avec les chemins absolus résolus."""
import argparse, pathlib, sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir",    required=True)
    p.add_argument("--keys-dir",   required=True)
    p.add_argument("--logs-dir",   required=True)
    p.add_argument("--baseline",   required=True)
    p.add_argument("--out",        required=True)
    p.add_argument("--log-level",  default="warn",
                   choices=["error", "warn", "info", "debug", "trace"],
                   help="verbosité sensor (défaut: warn pour prod, info pour démo)")
    a = p.parse_args()

    toml = f"""[sensor]
mode            = "monitor"
baseline_path   = "{a.baseline}"
baseline_output = "{a.baseline}"

# Production defaults — Phase Alpha requires maintenance window soak
[engine]
w_short      = 50
w_long       = 5000
warmup_ticks = 100

[alerting]
sinks       = ["ndjson"]
ndjson_path = "{a.logs_dir}/alerts.ndjson"
shadow_mode = false

[calibration]
signing_key       = "{a.keys_dir}/h7-cert-issuer.sec"
verifying_key     = "{a.keys_dir}/h7-cert-issuer.pub"
key_id            = "h7-demo-issuer"
require_signature = true

[runtime]
status_socket = "{a.run_dir}/status.sock"
log_level     = "{a.log_level}"
"""
    pathlib.Path(a.out).write_text(toml)
    print(f"  écrit : {a.out}")

if __name__ == "__main__":
    main()
