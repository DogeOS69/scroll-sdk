import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest


SPEC = importlib.util.spec_from_file_location(
    "balance_exporter", Path(__file__).resolve().parents[1] / "scripts/account-balance-exporter.py"
)
BALANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BALANCE)


class BalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                query = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.calls.append(query)
                if self.server.require_client_identity and self.headers.get("User-Agent") != "scroll-monitor-account-balances/0.1":
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"error code: 1010")
                    return
                if self.server.http_status:
                    self.send_response(self.server.http_status)
                    self.end_headers()
                    self.wfile.write(b"secret-provider-detail")
                    return
                if self.server.failure:
                    result = {"jsonrpc": "2.0", "id": 1, "error": {"message": "secret-provider-detail"}}
                else:
                    value = 1234 if query["method"] == "eth_chainId" else self.server.balance
                    result = {"jsonrpc": "2.0", "id": 1, "result": hex(value)}
                body = json.dumps(result).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.calls = []
        self.server.failure = False
        self.server.http_status = None
        self.server.require_client_identity = False
        self.server.balance = 5 * 10**18
        self.account = {"address": "0x" + "ab" * 20,
                        "rpc_url": f"http://127.0.0.1:{self.server.server_port}",
                        "expected_chain_id": "1234"}

    def test_rpc_reads_only_chain_id_and_latest_balance(self):
        result = BALANCE.collect(self.account, 1)
        self.assertEqual(result["balance"], 5 * 10**18)
        self.assertEqual(result["chain_id"], 1234)
        self.assertEqual([call["method"] for call in self.server.calls], ["eth_chainId", "eth_getBalance"])
        self.assertEqual(self.server.calls[1]["params"], [self.account["address"], "latest"])

    def test_zero_is_a_successful_balance_observation(self):
        self.server.balance = 0
        exporter = BALANCE.Exporter({"fee-oracle": self.account})
        exporter.refresh()
        rendered = exporter.render()
        self.assertIn('scroll_account_balance_scrape_success{account="fee-oracle"} 1', rendered)
        self.assertIn('chain_id="1234"} 0\n', rendered)

    def test_public_rpc_accepts_explicit_exporter_identity(self):
        self.server.require_client_identity = True
        exporter = BALANCE.Exporter({"eth-da-submitter": self.account})
        exporter.refresh()
        self.assertEqual(exporter.results["eth-da-submitter"]["success"], 1)
        self.assertEqual([call["method"] for call in self.server.calls], ["eth_chainId", "eth_getBalance"])

    def test_eth_units_and_fractional_default(self):
        self.server.balance = 10**17
        exporter = BALANCE.Exporter({"eth-da-submitter": self.account})
        exporter.refresh()
        self.assertIn('chain_id="1234"} 0.1\n', exporter.render())

    def test_failure_drops_stale_balance_without_exporting_zero_or_secrets(self):
        exporter = BALANCE.Exporter({"fee-oracle": self.account})
        exporter.refresh()
        last_success = exporter.results["fee-oracle"]["last_success"]
        self.server.failure = True
        exporter.refresh()
        rendered = exporter.render()
        self.assertNotIn("scroll_account_balance_eth{", rendered)
        self.assertIn('scroll_account_balance_scrape_success{account="fee-oracle"} 0', rendered)
        self.assertEqual(exporter.results["fee-oracle"]["last_success"], last_success)
        self.assertNotIn("secret-provider-detail", rendered)
        self.assertNotIn(self.account["rpc_url"], rendered)

    def test_wrong_chain_never_queries_balance(self):
        self.account["expected_chain_id"] = "1"
        with self.assertRaisesRegex(BALANCE.CollectionError, "wrong_chain"):
            BALANCE.collect(self.account, 1)
        self.assertEqual([c["method"] for c in self.server.calls], ["eth_chainId"])

    def test_http_failures_expose_bounded_reasons_without_false_balances(self):
        for status, reason in [(401, "rpc_access_denied"), (403, "rpc_access_denied"),
                               (429, "rpc_rate_limited"), (500, "rpc_http_error")]:
            with self.subTest(status=status):
                self.server.http_status = None
                exporter = BALANCE.Exporter({"eth-da-submitter": self.account})
                exporter.refresh()
                last_success = exporter.results["eth-da-submitter"]["last_success"]
                self.server.http_status = status
                exporter.refresh()
                rendered = exporter.render()
                self.assertIn(f'reason="{reason}"', rendered)
                self.assertNotIn("scroll_account_balance_eth{", rendered)
                self.assertNotIn("secret-provider-detail", rendered)
                self.assertNotIn(self.account["rpc_url"], rendered)
                self.assertEqual(exporter.results["eth-da-submitter"]["last_success"], last_success)

    def test_hex_expected_chain_id_is_supported(self):
        self.account["expected_chain_id"] = "0x4d2"
        self.assertEqual(BALANCE.collect(self.account, 1)["chain_id"], 1234)

    def test_missing_config_is_visible_for_both_accounts(self):
        exporter = BALANCE.Exporter(BALANCE.account_config({}))
        exporter.refresh()
        for account in ("fee-oracle", "eth-da-submitter"):
            self.assertEqual(exporter.results[account]["error"], "invalid_address")
        self.assertEqual(self.server.calls, [])

    def test_malformed_rpc_quantities_are_rejected(self):
        for value in (None, 0, "0", "-1", "0x", "0x00", "0x-1", "NaN"):
            with self.subTest(value=value):
                with self.assertRaises(BALANCE.CollectionError):
                    BALANCE.quantity(value)

    def test_one_bad_account_does_not_hide_another_accounts_balance(self):
        exporter = BALANCE.Exporter({"fee-oracle": {**self.account, "address": ""},
                                    "eth-da-submitter": self.account})
        exporter.refresh()
        self.assertEqual(exporter.results["fee-oracle"]["success"], 0)
        self.assertEqual(exporter.results["eth-da-submitter"]["success"], 1)

    def test_environment_variables_select_accounts_independently(self):
        env = {"SCROLL_BALANCE_FEE_ORACLE_ADDRESS": "0x" + "aa" * 20,
               "SCROLL_BALANCE_FEE_ORACLE_RPC_URL": "http://l2-rpc:8545",
               "SCROLL_BALANCE_ETH_DA_SUBMITTER_ADDRESS": "0x" + "bb" * 20,
               "SCROLL_BALANCE_ETH_DA_SUBMITTER_RPC_URL": "http://ethereum:8545"}
        accounts = BALANCE.account_config(env)
        self.assertEqual(accounts["fee-oracle"]["rpc_url"], "http://l2-rpc:8545")
        self.assertEqual(accounts["eth-da-submitter"]["address"], "0x" + "bb" * 20)


if __name__ == "__main__":
    unittest.main()
