# TERRA Unreal automation

`unreal_mcp_client.py` connects to Unreal Engine 5.8's built-in local MCP
server. The server is bound to the project-local editor session and should not
be exposed to the public network.

After saving and restarting Unreal Editor:

```bash
python3 Scripts/unreal_mcp_client.py ping
python3 Scripts/unreal_mcp_client.py list-tools
python3 Scripts/unreal_mcp_client.py call TOOL_NAME '{"argument": "value"}'
```

The project enables tool-search mode, so the initial list may contain the
`list_toolsets`, `describe_toolset`, and `call_tool` meta-tools rather than every
editor operation.
