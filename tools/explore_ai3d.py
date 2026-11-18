import json, sys, time, traceback
from gradio_client import Client, handle_file
SPACES = sys.argv[1:] or ["JeffreyXiang/TRELLIS", "tencent/Hunyuan3D-2", "stabilityai/stable-fast-3d", "VAST-AI/TripoSG", "tencent/Hunyuan3D-2.1", "microsoft/TRELLIS.2"]
for s in SPACES:
    print("=" * 30, s)
    try:
        c = Client(s, verbose=False)
        api = c.view_api(print_info=False, return_format="dict")
        for name, ep in api.get("named_endpoints", {}).items():
            ps = [(p.get("parameter_name"), p.get("component"), p.get("parameter_has_default"), str(p.get("parameter_default"))[:40]) for p in ep.get("parameters", [])]
            rs = [(r.get("label"), r.get("component")) for r in ep.get("returns", [])]
            print(name, "PARAMS", ps, "RETURNS", rs)
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:300])
