"""Corrected density sweep: one Simulate cycle per value (MI edits apply at PIE start)."""
import json, sys, time, subprocess
sys.path.insert(0, r"M:\claud_projects\temp\task5_visuals")
from cap import open_session

post, sid = open_session()
rid = 2600

def raw(ts, tool, args):
    global rid
    body, _ = post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                    "params": {"name": "call_tool",
                               "arguments": {"toolset_name": ts, "tool_name": tool,
                                             "arguments": args}}}, sid)
    rid += 1
    d = json.loads(body)
    return ("ERR " + json.dumps(d["error"])[:300]) if "error" in d else \
        " | ".join(p.get("text", "")[:300] for p in d["result"].get("content", []))

APP = "EditorToolset.EditorAppToolset"
MI = "/Game/SVT_REAL/MI_SvtPlayback.MI_SvtPlayback"
VIEWS = {"south": ("0", "-3500000", "300000", "8", "90"),
         "sw": ("-3200000", "-2700000", "350000", "6", "40")}

def shot(name, view):
    subprocess.run([sys.executable, "cap.py", name, *view],
                   check=True, cwd=r"M:\claud_projects\temp\task5_visuals")

for dv in [1.0, 5.0, 20.0]:
    r = raw("editor_toolset.toolsets.material_instance.MaterialInstanceTools",
            "set_scalar_parameter",
            {"instance": {"refPath": MI}, "name": "Density Scale", "value": dv})
    print("set density", dv, ":", r)
    time.sleep(2)
    print("StartPIE:", raw(APP, "StartPIE",
          {"options": {"bSimulate": True, "playMode": "PlayMode_Simulate", "warmupSeconds": 3}}))
    time.sleep(25)
    tag = ("%.0f" % dv) if dv >= 1 else ("%.1f" % dv).replace(".", "p")
    for vn, view in VIEWS.items():
        shot("sweep5_d%s_%s.png" % (tag, vn), view)
    print("StopPIE:", raw(APP, "StopPIE", {}))
    time.sleep(4)
    print("cycle done", dv, flush=True)
print("all done")
