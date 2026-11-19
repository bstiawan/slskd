#!/usr/bin/env python3
"""Minimal stdlib-only CLI for a released slskd 0.26.2 instance.

Reads a private JSON config ({"base_url": ..., "api_key": ...}) from
.local/ai-control/client.json beside this repository, or from --config.
Every command prints JSON to stdout and returns non-zero on failure.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_PREFIX = "/api/v0"
DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".local",
    "ai-control",
    "client.json",
)
DEFAULT_TIMEOUT = 30.0


class CliError(Exception):
    """Error surfaced to stderr with a non-zero exit."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects so the API key is never sent elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def build_opener():
    return urllib.request.build_opener(NoRedirect)


def redact(text, api_key):
    """Remove the API key from text destined for stderr."""
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text


def load_config(path):
    if not os.path.exists(path):
        raise CliError("config file not found: %s" % path)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CliError("cannot read config %s: %s" % (path, redact(str(exc), None))) from None

    if not isinstance(config, dict):
        raise CliError("config must be a JSON object")

    base_url = config.get("base_url")
    api_key = config.get("api_key")

    if not isinstance(base_url, str) or not base_url.strip():
        raise CliError("config missing string key: base_url")
    if not isinstance(api_key, str) or not api_key.strip():
        raise CliError("config missing string key: api_key")

    try:
        parsed = urllib.parse.urlsplit(base_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise CliError("invalid base_url: %s" % redact(str(exc), api_key)) from None

    if parsed.scheme not in ("http", "https"):
        raise CliError("base_url must use http or https")
    if parsed.username or parsed.password:
        raise CliError("base_url must not contain credentials")
    if not hostname:
        raise CliError("base_url must include a hostname")
    if port is not None and not (1 <= port <= 65535):
        raise CliError("base_url port must be between 1 and 65535")
    if parsed.query or parsed.fragment:
        raise CliError("base_url must not contain a query or fragment")

    return {"base_url": base_url.rstrip("/"), "api_key": api_key}


def encode_segment(value):
    """URL encode a single path segment, keeping '/' out of the result."""
    return urllib.parse.quote(str(value), safe="")


def request_json(config, method, path, payload=None, timeout=DEFAULT_TIMEOUT, opener=None):
    """Perform one API call and return (status_code, parsed_body_or_text)."""
    url = config["base_url"] + API_PREFIX + path
    data = None
    headers = {"X-API-Key": config["api_key"], "Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    if opener is None:
        opener = build_opener()

    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - best effort body read
            body = b""
    except urllib.error.URLError as exc:
        raise CliError("request to %s failed: %s" % (path, redact(str(exc.reason), config["api_key"]))) from None
    except (OSError, ValueError) as exc:
        raise CliError("request to %s failed: %s" % (path, redact(str(exc), config["api_key"]))) from None

    text = body.decode("utf-8", "replace").strip()
    if not text:
        return status, None

    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def emit(payload):
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def require_success(status, body, action):
    if status < 200 or status >= 300:
        detail = body if isinstance(body, str) else json.dumps(body)
        raise CliError("%s failed (HTTP %s): %s" % (action, status, detail))
    return body


def cmd_status(config, args):
    status, body = request_json(config, "GET", "/server", timeout=args.timeout)
    require_success(status, body, "status")
    emit(body)


def cmd_search(config, args):
    status, body = request_json(config, "POST", "/searches", {"searchText": args.text}, timeout=args.timeout)
    require_success(status, body, "search")
    emit(body)


def cmd_results(config, args):
    path = "/searches/%s/responses" % encode_segment(args.id)
    status, body = request_json(config, "GET", path, timeout=args.timeout)
    require_success(status, body, "results")
    emit(body)


def cmd_downloads(config, args):
    status, body = request_json(config, "GET", "/transfers/downloads", timeout=args.timeout)
    require_success(status, body, "downloads")
    emit(body)


def cmd_download(config, args):
    if args.size < 0:
        raise CliError("size must be zero or a positive integer")
    path = "/transfers/downloads/%s" % encode_segment(args.username)
    payload = [{"filename": args.file, "size": args.size}]
    status, body = request_json(config, "POST", path, payload, timeout=args.timeout)
    require_success(status, body, "download")
    emit(body)


def cmd_cancel(config, args):
    path = "/transfers/downloads/%s/%s" % (encode_segment(args.username), encode_segment(args.id))
    status, body = request_json(config, "DELETE", path, timeout=args.timeout)
    require_success(status, body, "cancel")
    emit(body)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="soulseek.py",
        description="Control a slskd instance over its HTTP API.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="path to JSON config (default: .local/ai-control/client.json)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="request timeout in seconds (default: %s)" % DEFAULT_TIMEOUT,
    )

    sub = parser.add_subparsers(dest="command")
    sub.required = True

    sub.add_parser("status", help="GET server state").set_defaults(func=cmd_status)

    search = sub.add_parser("search", help="start a search, returns the search object")
    search.add_argument("text", help="search text")
    search.set_defaults(func=cmd_search)

    results = sub.add_parser("results", help="list responses for a search id")
    results.add_argument("id", help="search id returned by search")
    results.set_defaults(func=cmd_results)

    sub.add_parser("downloads", help="list downloads").set_defaults(func=cmd_downloads)

    download = sub.add_parser("download", help="enqueue a single file download")
    download.add_argument("username", help="peer username")
    download.add_argument("--file", required=True, dest="file", help="remote file path")
    download.add_argument("--size", required=True, type=int, help="file size in bytes")
    download.set_defaults(func=cmd_download)

    cancel = sub.add_parser("cancel", help="cancel a queued or active download")
    cancel.add_argument("username", help="peer username")
    cancel.add_argument("id", help="transfer id")
    cancel.set_defaults(func=cmd_cancel)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    config = None

    try:
        config = load_config(args.config)
        if args.timeout <= 0:
            raise CliError("timeout must be a positive number")
        args.func(config, args)
    except CliError as exc:
        key = config.get("api_key") if config else None
        sys.stderr.write(redact(str(exc), key) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

