#!/usr/bin/env python3
"""Diagnose the Phase 10 cloud "Connection error" (Open issue #2).

The Agent dashboard reports the anthropic SDK's ``APIConnectionError``
("Connection error.") on ``claude-sonnet-4-6`` even though the API key is
present. That error means the HTTPS request never completed — a TLS / proxy /
DNS / certificate problem — and the *real* cause is wrapped inside it, which the
GUI hides. This script walks each layer from outside in and prints the hidden
cause, so we can tell where it breaks.

Run it on the Mac, from the repo root, with the SAME interpreter the sidecar
uses (the project venv), so the environment matches:

    cd ~/Codehome/AgenticOS
    ./.venv/bin/python scripts/diagnose_cloud.py

If the bug only reproduces in the Finder-launched .app (different env), also run
it from a shell launched the same way the app is. The API key is never printed —
only whether it's set, its length, and whether it has stray whitespace.

Paste the full output back.
"""
from __future__ import annotations

import os
import platform
import ssl
import subprocess
import sys
import traceback
from pathlib import Path

# Make `core` importable when run as `./.venv/bin/python scripts/diagnose_cloud.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODEL = "claude-sonnet-4-6"
API_HOST = "https://api.anthropic.com/v1/models"


def hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show_cause(exc: BaseException) -> None:
    """Print the exception plus its wrapped cause chain — the cause is usually
    the httpx/SSL error that actually explains an APIConnectionError."""
    print(f"  EXC: {type(exc).__module__}.{type(exc).__name__}: {exc}")
    seen = set()
    cur = exc.__cause__ or exc.__context__
    depth = 1
    while cur is not None and id(cur) not in seen and depth < 8:
        seen.add(id(cur))
        print(f"  CAUSE[{depth}]: {type(cur).__module__}.{type(cur).__name__}: {cur!r}")
        cur = cur.__cause__ or cur.__context__
        depth += 1
    print("  --- full traceback ---")
    traceback.print_exc()


def main() -> None:
    hr("0. Interpreter / platform")
    print(f"  python : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  macOS  : {platform.platform()}")
    print(f"  openssl: {ssl.OPENSSL_VERSION}")
    try:
        import certifi

        print(f"  certifi: {certifi.where()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  certifi: NOT importable — {exc}")

    hr("1. API key shape (value never printed)")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    print(f"  set            : {bool(key)}")
    print(f"  length         : {len(key)}")
    print(f"  stripped length: {len(key.strip())}  (mismatch ⇒ stray whitespace/newline!)")
    print(f"  prefix ok      : {key.strip().startswith('sk-ant-')}")

    hr("2. Env that can redirect/block egress")
    interesting = ("proxy", "anthropic", "ssl_cert", "requests_ca", "curl_ca",
                   "httpx", "no_proxy", "ca_bundle")
    found = {
        k: (v if "key" not in k.lower() else "<redacted>")
        for k, v in sorted(os.environ.items())
        if any(tok in k.lower() for tok in interesting)
    }
    print("  " + (str(found) if found else "(none of proxy/ANTHROPIC_BASE_URL/SSL_CERT/CA set)"))
    if os.environ.get("ANTHROPIC_BASE_URL"):
        print(f"  ⚠ ANTHROPIC_BASE_URL is set to {os.environ['ANTHROPIC_BASE_URL']!r} — the SDK")
        print("    will send 'cloud' requests THERE unless the caller pins base_url.")

    hr("3. Raw reachability via curl (bypasses Python entirely)")
    if not key:
        print("  skipped — no API key in env")
    else:
        try:
            out = subprocess.run(
                ["curl", "-sS", "-o", "/dev/null", "-w",
                 "http_code=%{http_code} connect=%{time_connect}s total=%{time_total}s\\n",
                 API_HOST,
                 "-H", f"x-api-key: {key}",
                 "-H", "anthropic-version: 2023-06-01"],
                capture_output=True, text=True, timeout=30,
            )
            print("  " + (out.stdout.strip() or "(no stdout)"))
            if out.stderr.strip():
                print("  stderr: " + out.stderr.strip())
            print("  → http_code 200 = network+TLS fine (problem is Python-side).")
            print("    http_code 000 = curl itself couldn't connect (proxy/DNS/TLS at OS level).")
        except Exception as exc:  # noqa: BLE001
            print(f"  curl failed to run: {exc}")

    hr("4. Direct httpx GET (the SDK's own HTTP stack)")
    if not key:
        print("  skipped — no API key in env")
    else:
        try:
            import httpx

            print(f"  httpx {httpx.__version__}")
            r = httpx.get(
                API_HOST,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                timeout=20,
            )
            print(f"  status {r.status_code} — body[:160]: {r.text[:160]!r}")
            print("  → 200 here but SDK fails ⇒ suspect SDK config/version, not the network.")
        except Exception as exc:  # noqa: BLE001
            print("  httpx GET raised — THIS cause is the smoking gun:")
            show_cause(exc)

    hr("5. anthropic SDK create() (what langchain-anthropic calls)")
    try:
        import anthropic

        print(f"  anthropic {anthropic.__version__}")
        client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY/ANTHROPIC_BASE_URL
        msg = client.messages.create(
            model=MODEL, max_tokens=16,
            messages=[{"role": "user", "content": "ping"}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content)
        print(f"  OK — reply: {text!r}")
    except Exception as exc:  # noqa: BLE001
        show_cause(exc)

    hr("6. Project layer: core.llm.complete() (exact sidecar path)")
    try:
        from core import llm

        res = llm.complete(
            [{"role": "user", "content": "ping"}], model=MODEL, max_tokens=16,
        )
        print(f"  OK — reply: {res.text!r}  tokens={res.tokens_used} cost=${res.cost_usd}")
    except Exception as exc:  # noqa: BLE001
        show_cause(exc)

    hr("Interpretation")
    print(
        "  curl 200 + httpx 200 + SDK fail  ⇒ SDK/langchain version or kwargs.\n"
        "  curl 200 + httpx FAIL            ⇒ Python TLS/cert (certifi) or proxy in-venv.\n"
        "  curl 000 / FAIL                  ⇒ OS-level network: proxy, VPN, DNS, firewall.\n"
        "  auth/4xx (not ConnectionError)   ⇒ key value/whitespace, not connectivity."
    )


if __name__ == "__main__":
    main()
