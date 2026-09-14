"""Agent 工具冒烟测试：无头启动一次仿真，逐个调用全部工具并报告结果。

用法（在 backend/ 下）：
    python scripts/check_agent_tools.py            # 默认 scheme_2
    python scripts/check_agent_tools.py official   # 换方案再测一遍
"""
import os
import sys
import time
import traceback

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.agent.tools import TOOL_SCHEMAS, execute_tool          # noqa: E402
from app.agent.agent import agent_status                        # noqa: E402
from app.algorithms.adapter import get_adapter                  # noqa: E402
from app.config import Settings                                 # noqa: E402
from app.core.runtime import AppRuntime                         # noqa: E402
from app.schemes import registry                               # noqa: E402


class _WS:
    def queue_put(self, *a, **k):
        return None

    def client_count(self):
        return 0


ACTION_BY_SCHEME = {
    "scheme_2": ("switch_mode", {"mode": "scoot"}),
    "official": ("switch_plan", {"plan": "平峰"}),
    "scheme_1": ("enable_green_wave", {}),
    "scheme_3": ("reroute_fleet", {}),
    "webster": ("get_status", {}),
}


def main():
    scheme = sys.argv[1] if len(sys.argv) > 1 else "scheme_2"
    net_dir = os.path.join(ROOT, "networks", "network")
    params = {
        "net_path": os.path.join(net_dir, "base_network.net.xml"),
        "route_files": [os.path.join(net_dir, "routes_clean700.rou.xml")],
        "add_files": [os.path.join(net_dir, "timing_safe.xml")],
        "scheme": scheme,
        "end": 3600,
        "speed": 20,
    }
    if scheme == "scheme_2":
        params["scheme_params"] = {
            "mode": "auto", "obs_mode": "agnostic",
            "mappo_weights": "models/weights/mappo_agnostic_full"}

    rt = AppRuntime(_WS(), Settings())
    print(f"=== scheme = {scheme} ===")
    print("start:", rt.start(params).get("session_id"))
    time.sleep(6)
    rt.pause()
    st = rt.status()
    print("state:", st["state"], "step:", st["step"])

    eng = rt.session.engine
    tls = eng.get_tls_ids()
    edges = [e for e in eng.get_edge_ids() if not e.startswith(":")]
    frm = to = None
    for e in edges:
        succ = eng.get_edge_successors(e)
        if succ:
            frm, to = e, succ[0]
            break
    print(f"tls={len(tls)} edges={len(edges)} route={frm}->{to}")
    print("registered algorithms:", [s["id"] for s in registry.list_schemes()])
    print("agent_status tools:", len(agent_status()["tools"]))
    print("-" * 78)

    def call(name, args, note=""):
        try:
            res = execute_tool(rt, name, args)
        except Exception:  # noqa: BLE001
            res = {"ok": False, "message": "抛异常: " + traceback.format_exc(limit=2)}
        flag = "OK  " if res.get("ok") else "FAIL"
        detail = res.get("message") or res.get("report") or ""
        if not detail and isinstance(res.get("data"), dict):
            keys = list(res["data"].keys())[:6]
            detail = "data keys=" + ",".join(keys)
        print(f"[{flag}] {name}{note}: {str(detail)[:160]}")
        return res

    # ── 逐个工具 ────────────────────────────────────────────
    call("get_network_status", {})
    call("get_tls_status", {"tls_id": tls[0] if tls else ""})
    call("get_tls_status", {"tls_id": "不存在的路口"}, note="(非法id,预期FAIL)")
    call("get_edge_status", {"edge_id": edges[0] if edges else ""})
    call("get_network_topology", {})
    call("get_region_status", {})
    call("get_region_status", {"edges": edges[:10]}, note="(指定边)")
    call("list_events", {})
    call("inject_event", {"event_type": "construction", "edge_ids": edges[:2]})
    call("list_events", {}, note="(注入后)")
    call("plan_route", {"from_edge": frm, "to_edge": to})
    call("plan_route", {"start": frm, "end": to}, note="(别名参数)")
    call("compare_metrics", {"action": "set"})
    call("compare_metrics", {"action": "compare"})
    call("compare_metrics", {"action": "clear"})
    call("generate_report", {})

    if scheme == "scheme_2":
        call("set_params", {"min_green": 5, "max_green": 40})
        call("switch_mode", {"mode": "scoot"})
        call("switch_mode", {"mode": "mappo"})
        call("switch_mode", {"mode": "auto"})

    # ── 标准化算法接口：对每个已注册算法测 config/action ────
    print("-" * 78)
    for sid in [s["id"] for s in registry.list_schemes()]:
        try:
            ad = get_adapter(rt, sid)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] adapter({sid}): {exc}")
            continue
        spec = ad.spec
        keys = [p.key for p in spec.params] if spec else []
        noop = {}
        if spec and spec.params:
            p = spec.params[0]
            noop = {p.key: p.default}
        call("configure_algorithm", {"algorithm_id": sid, "params": noop},
             note=f"({sid} 参数={keys[:5]})")
        act = ACTION_BY_SCHEME.get(sid)
        if act:
            call("algorithm_action", {"algorithm_id": sid, "action": act[0],
                                      "params": act[1]}, note=f"({sid}.{act[0]})")
    call("configure_algorithm", {"algorithm_id": "不存在的算法", "params": {}},
         note="(预期FAIL)")

    rt.stop()
    print("stopped.")


if __name__ == "__main__":
    main()
