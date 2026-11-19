#!/usr/bin/env python3
"""Isolated tests for scripts/soulseek.py using an injected mock transport.

Tests never touch the network: request_json accepts an opener, and the CLI is
driven through a fake opener so redirect handling and error paths are checked
without binding a socket.
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "soulseek.py")

_spec = importlib.util.spec_from_file_location("soulseek_cli", SCRIPT_PATH)
soulseek = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(soulseek)


class FakeResponse:
    """Minimal urlopen-style response."""

    def __init__(self, status=200, body=b"{}"):
        self._status = status
        self._body = body

    def getcode(self):
        return self._status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Records requests and returns a canned response or raises."""

    def __init__(self, status=200, body=b"{}", raises=None):
        self.records = []
        self.status = status
        self.body = body
        self.raises = raises

    def open(self, req, timeout=None):
        self.records.append(
            {
                "method": req.get_method(),
                "url": req.full_url,
                "api_key": req.get_header("X-api-key"),
                "content_type": req.get_header("Content-type"),
                "body": req.data.decode("utf-8") if req.data else None,
                "timeout": timeout,
            }
        )
        if self.raises is not None:
            raise self.raises
        return FakeResponse(self.status, self.body)


class CliTestCase(unittest.TestCase):
    PORT = 5030

    def setUp(self):
        self.opener = FakeOpener()
        self.saved_build = soulseek.build_opener
        soulseek.build_opener = lambda: self.opener
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp.name, "client.json")
        self.write_config("http://127.0.0.1:%d" % self.PORT, "secret-key-value")

    def tearDown(self):
        soulseek.build_opener = self.saved_build
        self.tmp.cleanup()

    def write_config(self, base_url, api_key):
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump({"base_url": base_url, "api_key": api_key}, handle)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = soulseek.main(["--config", self.config_path, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_status_sends_auth_header_and_gets_json(self):
        self.opener.body = json.dumps({"state": "Connected"}).encode()
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"state": "Connected"})
        self.assertEqual(len(self.opener.records), 1)
        rec = self.opener.records[0]
        self.assertEqual(rec["method"], "GET")
        self.assertEqual(rec["url"], "http://127.0.0.1:5030/api/v0/server")
        self.assertEqual(rec["api_key"], "secret-key-value")
        self.assertEqual(rec["timeout"], soulseek.DEFAULT_TIMEOUT)

    def test_search_posts_search_text(self):
        self.opener.body = json.dumps({"id": "abc", "searchText": "x"}).encode()
        code, _, _ = self.run_cli("search", "hello world")
        self.assertEqual(code, 0)
        rec = self.opener.records[0]
        self.assertEqual(rec["method"], "POST")
        self.assertEqual(rec["url"], "http://127.0.0.1:5030/api/v0/searches")
        self.assertEqual(rec["content_type"], "application/json")
        self.assertEqual(json.loads(rec["body"]), {"searchText": "hello world"})

    def test_results_path(self):
        code, _, _ = self.run_cli("results", "id-1")
        self.assertEqual(code, 0)
        self.assertEqual(self.opener.records[0]["url"], "http://127.0.0.1:5030/api/v0/searches/id-1/responses")

    def test_downloads_path(self):
        code, _, _ = self.run_cli("downloads")
        self.assertEqual(code, 0)
        self.assertEqual(self.opener.records[0]["url"], "http://127.0.0.1:5030/api/v0/transfers/downloads")

    def test_download_posts_single_file_body_and_escapes_username(self):
        code, _, _ = self.run_cli("download", "some user/name", "--file", "music/a b.mp3", "--size", "1234")
        self.assertEqual(code, 0)
        rec = self.opener.records[0]
        self.assertEqual(rec["method"], "POST")
        self.assertEqual(rec["url"], "http://127.0.0.1:5030/api/v0/transfers/downloads/some%20user%2Fname")
        self.assertEqual(json.loads(rec["body"]), [{"filename": "music/a b.mp3", "size": 1234}])

    def test_cancel_escapes_username_and_id(self):
        code, _, _ = self.run_cli("cancel", "user name", "id/slash")
        self.assertEqual(code, 0)
        rec = self.opener.records[0]
        self.assertEqual(rec["method"], "DELETE")
        self.assertEqual(rec["url"], "http://127.0.0.1:5030/api/v0/transfers/downloads/user%20name/id%2Fslash")

    def test_error_status_returns_nonzero_and_writes_stderr(self):
        self.opener.status = 500
        self.opener.body = b'{"error": "boom"}'
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("HTTP 500", err)

    def test_missing_config_file(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = soulseek.main(["--config", os.path.join(self.tmp.name, "nope.json"), "status"])
        self.assertEqual(code, 1)

    def test_config_rejects_userinfo_url(self):
        self.write_config("http://user:pass@127.0.0.1:%d" % self.PORT, "secret-key-value")
        code, _, _ = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertEqual(self.opener.records, [])

    def test_config_rejects_non_http_scheme(self):
        self.write_config("ftp://127.0.0.1:%d" % self.PORT, "secret-key-value")
        code, _, _ = self.run_cli("status")
        self.assertEqual(code, 1)

    def test_config_rejects_out_of_range_port(self):
        self.write_config("http://127.0.0.1:70000", "secret-key-value")
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("port", err.lower())

    def test_missing_api_key_key(self):
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump({"base_url": "http://127.0.0.1:%d" % self.PORT}, handle)
        code, _, _ = self.run_cli("status")
        self.assertEqual(code, 1)

    def test_api_key_not_leaked_in_error_output(self):
        self.opener.status = 500
        self.opener.body = b"secret-key-value leaked?"
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertNotIn("secret-key-value", err)

    def test_redirect_is_refused_and_key_not_forwarded(self):
        redirect = urllib.error.HTTPError(
            "http://127.0.0.1:5030/api/v0/server", 302, "redirect refused", {}, None
        )
        self.opener.raises = redirect
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.opener.records), 1)
        self.assertNotIn("secret-key-value", err)

    def test_no_redirect_handler_is_installed(self):
        opener = self.saved_build()
        handlers = [type(h).__name__ for h in opener.handlers]
        self.assertIn("NoRedirect", handlers)

    def test_negative_download_size_rejected(self):
        code, _, err = self.run_cli("download", "user", "--file", "a", "--size", "-5")
        self.assertEqual(code, 1)
        self.assertEqual(self.opener.records, [])
        self.assertIn("size", err)

    def test_nonpositive_timeout_rejected(self):
        code, _, err = self.run_cli("--timeout", "0", "status")
        self.assertEqual(code, 1)
        self.assertEqual(self.opener.records, [])
        self.assertIn("timeout", err)

    def test_timeout_is_passed_to_transport(self):
        code, _, _ = self.run_cli("--timeout", "12.5", "status")
        self.assertEqual(code, 0)
        self.assertEqual(self.opener.records[0]["timeout"], 12.5)

    def test_malformed_base_url_is_concise_error(self):
        self.write_config("http://[::1", "secret-key-value")
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertEqual(len(err.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
