#!/usr/bin/env python3
"""Small dependency-free client for Unreal Engine 5.8's local MCP server.

The Unreal MCP plugin is configured to listen on localhost only. This utility
performs the MCP handshake for each invocation and exposes safe inspection and
explicit tool calls from a terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = "2025-11-25"


class MCPError(RuntimeError):
    """Raised when Unreal MCP returns an invalid or error response."""


@dataclass
class UnrealMCPClient:
    endpoint: str = "http://127.0.0.1:8000/mcp"
    timeout: float = 30.0
    session_id: str | None = None
    protocol_version: str = PROTOCOL_VERSION
    _request_id: int = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(
        self,
        payload: dict[str, Any],
        *,
        include_session: bool = True,
        expect_json: bool = True,
    ) -> tuple[Any, dict[str, str], int]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if include_session and self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["Mcp-Protocol-Version"] = self.protocol_version

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            message = raw.decode("utf-8", errors="replace")
            raise MCPError(f"Unreal MCP HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(
                f"Cannot reach {self.endpoint}. Save and restart Unreal after enabling "
                "the ModelContextProtocol plugin, then try again."
            ) from exc

        if not expect_json or not raw:
            return None, response_headers, status

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MCPError(f"Unreal MCP returned non-JSON data: {raw[:500]!r}") from exc

        if isinstance(body, dict) and "error" in body:
            raise MCPError(json.dumps(body["error"], ensure_ascii=False))
        return body, response_headers, status

    def initialize(self) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "terra-codex",
                    "title": "TERRA Codex workspace client",
                    "version": "0.1.0",
                },
            },
        }
        body, headers, _ = self._post(payload, include_session=False)
        self.session_id = headers.get("mcp-session-id")
        if not self.session_id:
            raise MCPError("Unreal MCP initialize response omitted Mcp-Session-Id")
        self.protocol_version = body.get("result", {}).get("protocolVersion", PROTOCOL_VERSION)

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        self._post(notification, expect_json=False)
        return body

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.session_id:
            self.initialize()
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        body, _, _ = self._post(payload)
        return body.get("result") if isinstance(body, dict) else body

    def list_tools(self) -> Any:
        return self.request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self.request("tools/call", {"name": name, "arguments": arguments})


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("tool arguments must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--timeout", type=float, default=30.0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ping")
    subparsers.add_parser("list-tools")
    subparsers.add_parser("list-resources")
    call = subparsers.add_parser("call")
    call.add_argument("tool")
    call.add_argument("arguments", type=parse_json_object, nargs="?", default={})
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = UnrealMCPClient(endpoint=args.endpoint, timeout=args.timeout)
    try:
        if args.command == "ping":
            result = client.request("ping")
        elif args.command == "list-tools":
            result = client.list_tools()
        elif args.command == "list-resources":
            result = client.request("resources/list", {})
        else:
            result = client.call_tool(args.tool, args.arguments)
    except MCPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
