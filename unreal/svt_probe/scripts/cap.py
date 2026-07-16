"""Direct MCP-over-HTTP viewport capture: python cap.py out.png x y z pitch yaw"""
import json, sys, base64, http.client

def open_session():
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=300)
    def post(payload, sid=None):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if sid:
            headers["Mcp-Session-Id"] = sid
        conn.request("POST", "/mcp", json.dumps(payload), headers)
        resp = conn.getresponse()
        sid2 = resp.getheader("Mcp-Session-Id")
        ct = resp.getheader("Content-Type") or ""
        if "event-stream" not in ct:
            return resp.read().decode(), sid2
        data_lines, result = [], None
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode().rstrip("\r\n")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line == "" and data_lines:
                msg = "\n".join(data_lines); data_lines = []
                d = json.loads(msg)
                if d.get("id") == payload.get("id"):
                    result = msg
                    break
        # drain remaining body so the connection can be reused
        try:
            resp.read()
        except Exception:
            pass
        return result, sid2
    _, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "cap", "version": "1.0"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return post, sid

def call_tool(post, sid, toolset, tool, args, rid=2):
    body, _ = post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                    "params": {"name": "call_tool",
                               "arguments": {"toolset_name": toolset,
                                             "tool_name": tool,
                                             "arguments": args}}}, sid)
    d = json.loads(body)
    if "error" in d:
        raise RuntimeError(d["error"])
    content = d["result"]["content"][0]["text"]
    return json.loads(content)["returnValue"]

def main():
    out = sys.argv[1]
    x, y, z, pitch, yaw = map(float, sys.argv[2:7])
    post, sid = open_session()
    args = {"captureTransform": {"location": {"x": x, "y": y, "z": z},
                                 "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0}},
            "annotations": {"gridSpacing": 0, "gridExtent": 0, "gridHeight": 0,
                            "maxLabelDistance": 0, "classFilter": None, "maxLabels": 0},
            "bShowUI": False}
    rv = call_tool(post, sid, "EditorToolset.EditorAppToolset", "CaptureViewport", args)
    png = base64.b64decode(rv["image"]["data"])
    open(out, "wb").write(png)
    print("saved", out, len(png), "bytes")

if __name__ == "__main__":
    main()
