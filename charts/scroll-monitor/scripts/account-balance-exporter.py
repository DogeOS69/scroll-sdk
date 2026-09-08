#!/usr/bin/env python3
"""Read native account balances through JSON-RPC; never load signing keys."""

import json
import os
import re
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ACCOUNTS = {"fee-oracle": "FEE_ORACLE", "eth-da-submitter": "ETH_DA_SUBMITTER"}


class CollectionError(Exception):
    """A bounded error code that is safe to expose without RPC credentials."""


def quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise CollectionError("invalid_response")
    return int(value, 16)


def rpc(url, method, params, timeout):
    try:
        request = Request(url, data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise CollectionError("invalid_response")
        payload = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, HTTPException):
        raise CollectionError("rpc_unavailable") from None
    except (ValueError, UnicodeError):
        raise CollectionError("invalid_response") from None
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 1:
        raise CollectionError("invalid_response")
    if payload.get("error") is not None:
        raise CollectionError("rpc_error")
    return quantity(payload.get("result"))


def account_config(env):
    accounts = {}
    for account, prefix in ACCOUNTS.items():
        base = f"SCROLL_BALANCE_{prefix}_"
        accounts[account] = {
            "address": env.get(base + "ADDRESS", "").strip(),
            "rpc_url": env.get(base + "RPC_URL", "").strip(),
            "expected_chain_id": env.get(base + "EXPECTED_CHAIN_ID", "").strip(),
        }
    return accounts


def collect(account, timeout):
    address = account["address"]
    url = account["rpc_url"]
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise CollectionError("invalid_address")
    try:
        parsed = urlsplit(url)
        valid_url = parsed.scheme in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        valid_url = False
    if not valid_url:
        raise CollectionError("invalid_rpc_url")
    chain_id = rpc(url, "eth_chainId", [], timeout)
    expected = account["expected_chain_id"]
    if expected:
        try:
            expected_id = int(expected, 16 if expected.startswith("0x") else 10)
        except ValueError:
            raise CollectionError("invalid_chain_id") from None
        if chain_id != expected_id:
            raise CollectionError("wrong_chain")
    wei = rpc(url, "eth_getBalance", [address, "latest"], timeout)
    return {"balance": wei, "chain_id": chain_id, "address": address.lower()}


def labels(values):
    return "{" + ",".join(f"{key}={json.dumps(str(value))}" for key, value in values.items()) + "}"


class Exporter:
    def __init__(self, accounts, timeout=10):
        self.accounts = accounts
        self.timeout = timeout
        self.lock = threading.Lock()
        self.results = {name: {"success": 0, "last_success": 0, "error": "not_collected"}
                        for name in accounts}

    def refresh(self):
        for name, account in self.accounts.items():
            with self.lock:
                last_success = self.results[name]["last_success"]
            try:
                result = {**collect(account, self.timeout), "success": 1,
                          "last_success": time.time(), "error": "none"}
            except CollectionError as error:
                # Drop the previous balance on failure. Keeping it would make
                # stale funds look current; exporting zero would create a false
                # low-balance alert. Preserve only the last-success timestamp.
                result = {"success": 0, "last_success": last_success, "error": str(error)}
            with self.lock:
                self.results[name] = result

    def render(self):
        lines = [
            "# HELP scroll_account_balance_eth Native balance in units of 1e18 wei.",
            "# TYPE scroll_account_balance_eth gauge",
            "# HELP scroll_account_balance_scrape_success Whether the latest RPC collection succeeded.",
            "# TYPE scroll_account_balance_scrape_success gauge",
            "# HELP scroll_account_balance_last_success_timestamp_seconds Last successful balance observation.",
            "# TYPE scroll_account_balance_last_success_timestamp_seconds gauge",
            "# HELP scroll_account_balance_collection_status Latest bounded collection status.",
            "# TYPE scroll_account_balance_collection_status gauge",
        ]
        with self.lock:
            snapshot = dict(self.results)
        for name, result in snapshot.items():
            account = labels({"account": name})
            lines.append(f'scroll_account_balance_scrape_success{account} {result["success"]}')
            lines.append(f'scroll_account_balance_last_success_timestamp_seconds{account} {result["last_success"]}')
            status = labels({"account": name, "reason": result["error"]})
            lines.append(f"scroll_account_balance_collection_status{status} 1")
            if result["success"]:
                identity = labels({"account": name, "address": result["address"], "chain_id": result["chain_id"]})
                # Format exactly in decimal before Prometheus converts to float.
                balance = Decimal(result["balance"]) / Decimal(10**18)
                lines.append(f"scroll_account_balance_eth{identity} {balance:f}")
        return "\n".join(lines) + "\n"


def serve(exporter, interval, port=9108):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/metrics", "/healthz"):
                self.send_error(404)
                return
            body = exporter.render().encode() if self.path == "/metrics" else b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    def poll():
        while True:
            exporter.refresh()
            time.sleep(interval)

    threading.Thread(target=poll, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    interval = int(os.environ.get("SCROLL_BALANCE_INTERVAL_SECONDS", "60"))
    timeout = int(os.environ.get("SCROLL_BALANCE_RPC_TIMEOUT_SECONDS", "10"))
    if not 1 <= interval <= 120 or not 1 <= timeout <= 15:
        raise SystemExit("Balance interval must be 1..120s and RPC timeout 1..15s")
    serve(Exporter(account_config(os.environ), timeout), interval)
