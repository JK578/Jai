import json

import pytest
from incidentiq.mcp_server import MCPServer


def request(server, method, **params):
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def test_lifecycle_scope_filter_and_read_only_boundary():
    calls = []

    def get(path, params):
        calls.append((path, params))
        return {"scopes": ["logs:read"]} if path.endswith("session") else {"items": []}

    server = MCPServer(get)
    assert request(server, "tools/list")["error"]["code"] == -32002
    assert "result" in request(server, "initialize")
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = request(server, "tools/list")["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"list_log_files", "read_logs", "get_log"}
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    assert request(server, "tools/call", name="list_incidents")["error"]["code"] == -32001
    assert request(server, "tools/call", name="execute_sql")["error"]["code"] == -32602
    result = request(server, "tools/call", name="list_log_files")["result"]
    assert result["structuredContent"]["untrusted_evidence"] is True
    assert json.loads(result["content"][0]["text"])["data"] == {"items": []}
    assert calls[-1] == ("/api/v1/log-datasets", {})


@pytest.mark.parametrize(
    "arguments",
    [
        {"file_id": "../../secrets"},
        {"file_id": "00000000-0000-0000-0000-000000000001", "limit": 21},
        {"file_id": "00000000-0000-0000-0000-000000000001", "limit": "10"},
        {"file_id": "00000000-0000-0000-0000-000000000001", "sql": "SELECT 1"},
    ],
)
def test_invalid_arguments_never_reach_backend(arguments):
    calls = []

    def get(path, params):
        calls.append(path)
        return {"scopes": ["logs:read"]}

    server = MCPServer(get)
    request(server, "initialize")
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert (
        request(server, "tools/call", name="read_logs", arguments=arguments)["error"]["code"]
        == -32602
    )
    assert calls == ["/api/v1/auth/session"]


def test_revoked_token_is_checked_again_and_error_is_sanitized():
    def get(path, params):
        if path.endswith("session"):
            return {"scopes": ["logs:read"]}
        raise PermissionError("private credential must not escape")

    server = MCPServer(get)
    request(server, "initialize")
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = request(server, "tools/call", name="list_log_files")
    assert response["result"]["isError"] is True
    assert "private credential" not in json.dumps(response)


def test_failed_authentication_cannot_initialize():
    def denied(path, params):
        raise PermissionError

    server = MCPServer(denied)
    assert request(server, "initialize")["error"]["code"] == -32001
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert request(server, "tools/list")["error"]["code"] == -32002
