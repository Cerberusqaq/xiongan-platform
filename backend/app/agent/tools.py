"""LLM Agent 工具集：感知/行动，全部映射到平台已有能力（runtime / scheme / events）。

安全护栏：参数白名单 + 数值范围校验，LLM 输出经校验后才允许执行。
"""

import json


# ── 工具 JSON Schema（供 function calling） ─────────────────

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_network_status",
        "description": "获取路网全局实时指标（在网车辆数、平均速度、平均等待时间、平均排队）（速度单位 m/s，汇报请换算为 km/h）",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_tls_status",
        "description": "获取信号路口状态：当前相位、相位时长，以及各进口边的排队车辆数（判断哪个方向长期未放行/饿死）。tls_id 传路口编号（如 \"1\"），传 all 或不传可一次返回全部路口概要；注意这里要的是路口 id，不是道路 id（传道路 id 会自动解析到其受控路口）",
        "parameters": {"type": "object",
                       "properties": {"tls_id": {"type": "string",
                                                 "description": "路口 id（如 \"1\"；all=全部路口）"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "get_edge_status",
        "description": "获取某条道路的实时状态（车辆数、平均速度、占有率、限速），用于评估通行/给出建议车速（速度单位 m/s，汇报请换算为 km/h）",
        "parameters": {"type": "object",
                       "properties": {"edge_id": {"type": "string", "description": "道路 id"}},
                       "required": ["edge_id"]}}},
    {"type": "function", "function": {
        "name": "plan_route",
        "description": "为车辆规划最优行车路径（Dijkstra，按实时旅行时间加权），返回建议路线边序列与预计行程时间，用于驾驶/绕行建议",
        "parameters": {"type": "object",
                       "properties": {
                           "from_edge": {"type": "string", "description": "起点边 id"},
                           "to_edge": {"type": "string", "description": "终点边 id"}},
                       "required": ["from_edge", "to_edge"]}}},
    {"type": "function", "function": {
        "name": "list_events",
        "description": "列出已注入的扰动事件（施工/突发车流/事故）",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "inject_event",
        "description": "注入扰动事件：construction(施工限速) / large_event(突发车流) / accident(事故限速)",
        "parameters": {"type": "object",
                       "properties": {
                           "event_type": {"type": "string",
                                          "enum": ["construction", "large_event", "accident"]},
                           "edge_ids": {"type": "array", "items": {"type": "string"},
                                        "description": "受影响边"},
                           "vehicles": {"type": ["integer", "array"],
                                        "description": "突发车流的车辆数（large_event 用；传数组时按元素个数计）"}},
                       "required": ["event_type"]}}},
    {"type": "function", "function": {
        "name": "set_params",
        "description": "调整方案二控制器参数（MAPPO/SCOOT）：min_green 最短绿灯(s)、max_green 最长绿灯(s)、switch_clearance 变灯倒计时(s)",
        "parameters": {"type": "object",
                       "properties": {
                           "min_green": {"type": "number", "minimum": 0, "maximum": 20},
                           "max_green": {"type": "number", "minimum": 15, "maximum": 90},
                           "switch_clearance": {"type": "number", "minimum": 5, "maximum": 20}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "switch_mode",
        "description": "切换方案二控制器模式：mappo（AI 强化学习控制）/ scoot（规则自适应）/ auto（按可用性自动选择）",
        "parameters": {"type": "object",
                       "properties": {"mode": {"type": "string",
                                               "enum": ["mappo", "scoot", "auto"]}},
                       "required": ["mode"]}}},
    {"type": "function", "function": {
        "name": "get_custom_metrics",
        "description": "获取自定义指标：完成率、累计出发/到达、最久行程车辆、最久等待车辆、最堵道路（most_congested_edge）、最堵路口（most_congested_tls），用于找出最堵的路段与路口",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_algorithm_state",
        "description": "读取某算法（默认当前激活算法）的当前参数、框架统一观测快照与算法内部指标（如方案二 MAPPO/SCOOT 决策计数、观测维度、奖励权重）",
        "parameters": {"type": "object",
                       "properties": {"algorithm_id": {"type": "string",
                                                       "description": "算法 id（可选，默认当前激活算法）"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "switch_scheme",
        "description": "切换当前控制方案（scheme_1 方案一 / scheme_2 方案二 / scheme_3 方案三 / official 官方方案 / webster）。注意：切换会以同一路网与车流重启仿真，步数与在网车辆会重置——回复里必须说明这一点",
        "parameters": {"type": "object",
                       "properties": {"algorithm_id": {"type": "string",
                                                       "enum": ["scheme_1", "scheme_2", "scheme_3",
                                                                "official", "webster"]}},
                       "required": ["algorithm_id"]}}},
    {"type": "function", "function": {
        "name": "set_right_turn_green",
        "description": "开启/关闭右转常绿（路口信号程序级开关，仿真运行中即时生效、关闭时自动还原原程序）。注意：这不是算法参数，不能用 configure_algorithm 设置",
        "parameters": {"type": "object",
                       "properties": {"enabled": {"type": "boolean",
                                                  "description": "true=开启右转常绿，false=关闭并还原"}},
                       "required": ["enabled"]}}},
    {"type": "function", "function": {
        "name": "generate_report",
        "description": "生成一份当前路网态势报告（Markdown）：在网车辆、平均速度、平均等待/排队、累计到达、活跃事件。用户说\"生成报告/态势报告/出一份报告\"时必须调用本工具（get_network_status 只是原始指标，不能代替报告）",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_network_topology",
        "description": "获取路网拓扑：路口（含关键路口/信号灯）、边（车道数/限速）、主干道、边邻接关系，用于路网级规划与走廊识别",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_region_status",
        "description": "获取一片区域的聚合实时指标（车辆数/平均速度/排队/拥堵度）。两种用法：region 传方位（东/南/西/北/中心，后端按路网坐标自动解析为道路集合，适合「东侧拥堵」这类说法）；或 edges 传边 id 列表。都不传则覆盖全路网（速度单位 m/s，汇报请换算为 km/h）",
        "parameters": {"type": "object",
                       "properties": {"edges": {"type": "array", "items": {"type": "string"},
                                                "description": "区域包含的边 id 列表（可选）"},
                                      "region": {"type": "string",
                                                 "description": "方位区域：东/南/西/北/中心（可选，与 edges 二选一）"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "configure_algorithm",
        "description": "设置标准化算法参数（scheme_2 的 min_green/max_green/mode、official 官方方案的 mode/decision_step、scheme_1 的 green_wave/recalc_interval、scheme_3 的 auto_reroute 等），按算法声明校验",
        "parameters": {"type": "object",
                       "properties": {
                           "algorithm_id": {"type": "string", "description": "算法 id：scheme_1 / scheme_2 / scheme_3 / official"},
                           "params": {"type": "object", "description": "要设置的参数键值对"}},
                       "required": ["algorithm_id", "params"]}}},
    {"type": "function", "function": {
        "name": "algorithm_action",
        "description": "调用标准化算法通用动作：switch_mode(切 MAPPO/SCOOT/auto)、switch_plan(官方方案切早高峰/平峰/晚高峰档)、enable_green_wave(开绿波)、reroute_fleet(车队重路由)、add_restricted_zone(限行) 等",
        "parameters": {"type": "object",
                       "properties": {
                           "algorithm_id": {"type": "string", "description": "算法 id：scheme_1 / scheme_2 / scheme_3 / official"},
                           "action": {"type": "string", "description": "动作名（见 /algorithms 能力清单）"},
                           "params": {"type": "object", "description": "动作参数（可选）"}},
                       "required": ["algorithm_id", "action"]}}},
    {"type": "function", "function": {
        "name": "compare_metrics",
        "description": "对比调控前后指标：action=set 记录当前指标为基线；action=compare 与基线对比返回差异（对比后清除基线）；action=clear 清除基线（返回速度单位 m/s，汇报请换算为 km/h）",
        "parameters": {"type": "object",
                       "properties": {"action": {"type": "string",
                                                 "enum": ["set", "compare", "clear"],
                                                 "default": "compare"}},
                       "required": []}}},
]


def _safe_params(schema, args):
    """参数校验：类型 + 枚举白名单 + 数值范围。

    类型必须真正校验：模型常把数组/列表塞进字符串参数（如 tls_id=["1","2"]），
    不拦就会拿着非法类型去查 TraCI 并抛出难懂的错误。
    """
    params = schema.get("function", {}).get("parameters", {})
    props = params.get("properties", {})
    out = {}
    for k, v in (args or {}).items():
        spec = props.get(k, {})
        ptype = spec.get("type")
        if ptype == "string" and not isinstance(v, str):
            return None, (f"参数 {k} 需为字符串（收到 {type(v).__name__}）；"
                          f"多个值请分开多次调用")
        if ptype == "array" and isinstance(v, str):
            # 宽容：模型常把列表参数写成 "E1,E2" 这种逗号串
            v = [s.strip() for s in v.split(",") if s.strip()]
        if ptype == "array" and not isinstance(v, list):
            return None, f"参数 {k} 需为数组（收到 {type(v).__name__}）"
        if ptype == "object" and not isinstance(v, dict):
            return None, f"参数 {k} 需为对象（收到 {type(v).__name__}）"
        if ptype == "boolean" and not isinstance(v, bool):
            if isinstance(v, str) and v.strip().lower() in ("true", "false", "1", "0"):
                v = v.strip().lower() in ("true", "1")
            else:
                return None, f"参数 {k} 需为 true/false（收到 {v!r}）"
        if ptype in ("number", "integer"):
            try:
                v = float(v)
                if ptype == "integer":
                    v = int(v)
            except (TypeError, ValueError):
                return None, f"参数 {k} 需为数字（收到 {type(v).__name__}）"
        if spec.get("enum"):
            if isinstance(v, str):
                # 容错：忽略大小写与首尾空格（LLM 常把 SCOOT/MAPPO 写成大写）
                key = v.strip().lower()
                hit = next((e for e in spec["enum"]
                            if str(e).strip().lower() == key), None)
                if hit is None:
                    return None, f"参数 {k}={v} 不在允许范围 {spec['enum']}"
                v = hit
            elif v not in spec["enum"]:
                return None, f"参数 {k}={v} 不在允许范围 {spec['enum']}"
        lo, hi = spec.get("minimum"), spec.get("maximum")
        if isinstance(v, (int, float)) and lo is not None and v < lo:
            return None, f"参数 {k}={v} 低于下限 {lo}"
        if isinstance(v, (int, float)) and hi is not None and v > hi:
            return None, f"参数 {k}={v} 超过上限 {hi}"
        out[k] = v
    return out, None


def execute_tool(runtime, name: str, args: dict) -> dict:
    """执行工具调用：与仿真线程串行（共用同一个 TraCI 连接，不能并发读）。

    仿真进行中 Agent 查指标/调参同样会走 TraCI，与仿真线程的 step 并发会导致
    响应错位；故统一用 runtime 的方案锁串行（RLock，可重入）。
    """
    lock = getattr(runtime, "_scheme_lock", None)
    if lock is None:
        return _execute_tool(runtime, name, args)
    with lock:
        return _execute_tool(runtime, name, args)


def _execute_tool(runtime, name: str, args: dict) -> dict:
    """执行工具调用。返回 (ok, 结果文本) 结构化 dict，带安全护栏。"""
    schema = next((t for t in TOOL_SCHEMAS
                   if t["function"]["name"] == name), None)
    if schema is None:
        return {"ok": False, "message": f"未知工具: {name}"}
    args, err = _safe_params(schema, args)
    if err:
        return {"ok": False, "message": f"参数校验失败: {err}"}

    try:
        # 引擎访问：平台 runtime 为 session.engine，演示 DemoRuntime 直接为 engine
        eng = (getattr(runtime, "engine", None)
               or getattr(getattr(runtime, "session", None), "engine", None))
        if name == "get_network_status":
            m = runtime.realtime_metrics().get("overall", {})
            return {"ok": True, "data": {
                "vehicle_count": m.get("vehicle_count"),
                "avg_speed": m.get("avg_speed"),
                "avg_waiting_time": m.get("avg_waiting_time"),
                "avg_queue_length": m.get("avg_queue_length")}}
        if name == "get_tls_status":
            tid = str(args.get("tls_id") or "").strip()
            tls_ids = [str(t) for t in (eng.get_tls_ids() or [])]
            # 不传 / all：一次返回全部路口概要（模型常不知道路口 id，避免空转）
            if not tid or tid.lower() in ("all", "*", "all_tls", "全部", "所有"):
                return {"ok": True, "data": {
                    "count": len(tls_ids),
                    "intersections": [_tls_brief(eng, t) for t in tls_ids[:40]]}}
            if tid not in tls_ids:
                # 容错：模型常把"边 id"当成"路口 id"传进来，自动解析到受控路口
                guess = _resolve_tls_by_edge(eng, tid, tls_ids)
                if guess:
                    tid = guess
                else:
                    return {"ok": False,
                            "message": (f"信号灯不存在: {tid}。路口 id 形如 {tls_ids[:6]}…"
                                        f"（可用 all 一次查看全部）；查某条道路请用 get_edge_status")}
            return {"ok": True, "data": _tls_detail(eng, tid)}
        if name == "get_edge_status":
            eid = args.get("edge_id", "")
            stats = eng.get_edge_stats(eid)
            return {"ok": True, "data": {
                "edge_id": eid,
                "vehicle_count": stats["vehicle_count"],
                "mean_speed": round(stats["mean_speed"], 2),
                "occupancy": round(stats["occupancy"], 3),
                "speed_limit": round(eng.get_edge_speed_limit(eid), 2)}}
        if name == "plan_route":
            # 兼容小模型常见参数名：from_edge/to_edge 或 start/end 或 from/to
            frm = args.get("from_edge") or args.get("start") or args.get("from") or ""
            to = args.get("to_edge") or args.get("end") or args.get("to") or ""
            path, cost = _dijkstra(eng, frm, to)
            if path is None:
                return {"ok": False, "message": f"起点 {frm} 到终点 {to} 不可达"}
            return {"ok": True, "data": {
                "from_edge": frm, "to_edge": to,
                "route_edges": path,
                "travel_time_s": round(cost, 1)}}
        if name == "list_events":
            return {"ok": True, "data": runtime.list_events()}
        if name == "inject_event":
            veh = args.get("vehicles", 20)
            if isinstance(veh, (list, tuple)):   # 模型有时传车辆 id 列表 → 按个数计
                veh = len(veh)
            result = runtime.inject_event(
                args.get("event_type"), {
                    "edge_ids": args.get("edge_ids", []),
                    "vehicles": veh})
            return {"ok": True, "message": f"已注入 {args.get('event_type')}: {result}"}
        if name == "set_params":
            # 统一走标准化适配器：按当前算法的 ParamSpec 校验，未声明参数直接报错，
            # 避免"返回 ok 但一个参数都没改"（如 official 只认 mode/decision_step/cooldown）
            if runtime.scheme is None:
                return {"ok": False, "message": "仿真未启动或无方案激活"}
            return _tool_configure_algorithm(
                runtime, {"algorithm_id": runtime.scheme.name, "params": args})
        if name == "switch_mode":
            if runtime.scheme is None or runtime.scheme.name != "scheme_2":
                cur = getattr(runtime.scheme, "name", "none")
                return {"ok": False,
                        "message": f"方案二未激活（当前算法：{cur}），无法切换模式"}
            action = {"mappo": "switch_to_mappo", "scoot": "switch_to_scoot",
                      "auto": "switch_to_auto"}.get(str(args.get("mode", "")).lower())
            if action is None:
                return {"ok": False, "message": "mode 需为 mappo / scoot / auto"}
            return runtime.scheme.handle_action(action, {})
        if name == "set_right_turn_green":
            if runtime.session is None:
                return {"ok": False, "message": "仿真未启动，无法设置右转常绿"}
            raw = args.get("enabled", True)
            if isinstance(raw, str):
                enabled = raw.strip().lower() not in ("false", "0", "no", "off", "关闭")
            else:
                enabled = bool(raw)
            res = runtime.set_right_turn_green(enabled)
            if not res.get("ok"):
                return {"ok": False, "message": "仿真未启动，无法设置右转常绿"}
            return {"ok": True, "data": {"right_turn_green": enabled},
                    "message": "已开启右转常绿" if enabled else "已关闭右转常绿并还原原程序"}
        if name == "get_custom_metrics":
            # 平台"自定义指标"：完成率/累计出发到达/最久车辆/最堵道路/最堵路口
            # （原先只有 REST /metrics/spotlight 暴露，Agent 无法查询）
            return {"ok": True, "data": runtime.spotlight()}
        if name == "get_algorithm_state":
            return _tool_algorithm_state(runtime, args)
        if name == "switch_scheme":
            aid = str(args.get("algorithm_id") or args.get("scheme_id") or "")
            if not aid:
                return {"ok": False,
                        "message": "需要 algorithm_id（scheme_1/scheme_2/scheme_3/official/webster）"}
            try:
                return runtime.switch_scheme(aid)
            except Exception as exc:  # noqa: BLE001 未知方案/未启动等给出可读原因
                return {"ok": False, "message": f"切换方案失败: {exc}"}
        if name == "generate_report":
            m = runtime.realtime_metrics().get("overall", {})
            st = runtime.status()
            lines = [
                f"# 态势报告（仿真步 {st.get('step')}）",
                f"- 在网车辆：{m.get('vehicle_count')}",
                f"- 平均速度：{round((m.get('avg_speed') or 0) * 3.6, 1)} km/h",
                f"- 平均等待：{m.get('avg_waiting_time')} s",
                f"- 平均排队：{m.get('avg_queue_length')} 辆",
                f"- 累计到达：{m.get('total_throughput')}",
            ]
            events = runtime.list_events()
            if events:
                lines.append("- 活跃事件：" + "、".join(e["event_type"] for e in events[-3:]))
            return {"ok": True, "report": "\n".join(lines)}
        if name == "get_network_topology":
            return _tool_topology(runtime, eng)
        if name == "get_region_status":
            edges = list(args.get("edges") or [])
            region = str(args.get("region") or "").strip()
            if not edges and region:
                # 方位词（东/南/西/北/中心）→ 具体边集合，避免模型瞎猜边 id
                edges, err = _resolve_region_edges(runtime, region)
                if err:
                    return {"ok": False, "message": err}
                if not edges:
                    return {"ok": False,
                            "message": f"区域「{region}」未匹配到任何道路，请改用边 id 列表"}
            res = _tool_region_status(eng, edges)
            if region and isinstance(res.get("data"), dict):
                res["data"]["region"] = region
                res["data"]["region_edges_sample"] = edges[:10]
            return res
        if name == "configure_algorithm":
            return _tool_configure_algorithm(runtime, args)
        if name == "algorithm_action":
            return _tool_algorithm_action(runtime, args)
        if name == "compare_metrics":
            return _tool_compare_metrics(runtime, args.get("action", "compare"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"工具执行失败: {type(exc).__name__}: {exc}"}
    return {"ok": False, "message": f"未处理工具: {name}"}


def _tls_detail(eng, tid: str) -> dict:
    """单个路口：相位信息 + 各进口边排队（识别未放行/饿死方向的依据）。"""
    st = eng.get_tls_state(tid)
    approach_q: dict[str, int] = {}
    try:
        for lk in eng.get_tls_links(tid):
            e = str(lk.get("from_edge") or "")
            if e and e not in approach_q:
                approach_q[e] = int(eng.get_edge_queue(e))
    except Exception:  # noqa: BLE001
        approach_q = {}
    ranked = sorted(approach_q.items(), key=lambda kv: -kv[1])[:3]
    return {"tls_id": tid, "phase_index": st["phase_index"],
            "num_phases": st["num_phases"],
            "phase_duration": st["phase_duration"],
            "state_str": st.get("state_str", ""),
            "approach_queues": approach_q,
            "worst_approaches": [{"edge": e, "queue": q} for e, q in ranked]}


def _tls_brief(eng, tid: str) -> dict:
    """路口概要（不含全量进口排队，供"一次查全部路口"）。"""
    d = _tls_detail(eng, tid)
    total = sum(d["approach_queues"].values())
    return {"tls_id": tid, "phase_index": d["phase_index"],
            "num_phases": d["num_phases"], "queue_total": total,
            "worst_approaches": d["worst_approaches"]}


def _resolve_tls_by_edge(eng, edge_like: str, tls_ids: list[str]) -> str | None:
    """把边 id（或形如 E12_8 的串）解析到受其控制的信号灯。"""
    if not edge_like:
        return None
    try:
        for tid in tls_ids:
            for lk in eng.get_tls_links(tid):
                if str(lk.get("from_edge") or "") == edge_like:
                    return tid
    except Exception:  # noqa: BLE001
        return None
    return None


_REGION_ALIASES = {
    "东": "east", "东侧": "east", "东边": "east", "东部": "east",
    "西": "west", "西侧": "west", "西边": "west", "西部": "west",
    "南": "south", "南侧": "south", "南边": "south", "南部": "south",
    "北": "north", "北侧": "north", "北边": "north", "北部": "north",
    "中心": "center", "中部": "center", "中央": "center", "中间": "center",
    "east": "east", "west": "west", "south": "south", "north": "north",
    "center": "center", "centre": "center",
}


def _resolve_region_edges(runtime, region: str) -> tuple[list[str], str]:
    """方位区域 → 边集合（按路网节点坐标自动划分东/南/西/北/中心）。

    返回 (边 id 列表, 错误信息)。模型说"东侧拥堵"时无法直接给边 id，
    这里把方位词落到具体道路上，避免它瞎猜 id。
    """
    gj = getattr(runtime, "_geojson", None) or {}
    nodes: dict[str, tuple[float, float]] = {}
    edges: list[dict] = []
    for f in gj.get("features", []) or []:
        geom = (f.get("geometry") or {}).get("type")
        p = f.get("properties") or {}
        if geom == "Point":
            coord = (f.get("geometry") or {}).get("coordinates") or []
            if len(coord) >= 2:
                nodes[str(p.get("node_id"))] = (float(coord[0]), float(coord[1]))
        elif geom == "LineString":
            edges.append({"id": p.get("edge_id"), "from": p.get("from_node")})
    if not nodes or not edges:
        return [], "路网数据缺失，无法按方位解析区域"
    key = _REGION_ALIASES.get(str(region).strip().lower()) or \
        _REGION_ALIASES.get(str(region).strip())
    if key is None:
        return [], (f"无法识别方位「{region}」，可用：东/南/西/北/中心")
    xs = [c[0] for c in nodes.values()]
    ys = [c[1] for c in nodes.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sx = max(1e-6, (max(xs) - min(xs)) / 4)
    sy = max(1e-6, (max(ys) - min(ys)) / 4)
    out: list[str] = []
    for e in edges:
        pos = nodes.get(str(e.get("from")))
        if pos is None or not e.get("id"):
            continue
        x, y = pos
        if key == "east" and x >= cx + sx:
            out.append(e["id"])
        elif key == "west" and x <= cx - sx:
            out.append(e["id"])
        elif key == "north" and y >= cy + sy:
            out.append(e["id"])
        elif key == "south" and y <= cy - sy:
            out.append(e["id"])
        elif key == "center" and abs(x - cx) <= sx and abs(y - cy) <= sy:
            out.append(e["id"])
    return out, ""


def _dijkstra(eng, frm: str, to: str):
    """Dijkstra 最优路径（按实时旅行时间加权）。返回 (边序列, 总时间) 或 (None, inf)。"""
    import heapq
    if not frm or not to:
        return None, float("inf")
    INF = float("inf")
    dist = {frm: 0.0}
    prev: dict[str, str] = {}
    pq = [(0.0, frm)]
    visited: set[str] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == to:
            break
        for v in eng.get_edge_successors(u):
            if v in visited:
                continue
            try:
                tt = eng.get_edge_stats(v).get("travel_time", INF)
            except Exception:  # noqa: BLE001
                tt = INF
            if tt == INF or tt <= 0:
                tt = 1.0
            nd = d + tt
            if nd < dist.get(v, INF):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if to not in dist:
        return None, INF
    path = [to]
    u = to
    while u != frm:
        u = prev.get(u)
        if u is None:
            return None, INF
        path.append(u)
    path.reverse()
    return path, dist[to]


# ── 路网级规划工具 ─────────────────────────────────────────

def _tool_topology(runtime, eng) -> dict:
    """路网拓扑：路口（关键/信号灯）、边（车道/限速）、主干道、邻接。"""
    gj = getattr(runtime, "_geojson", None)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for f in (gj.get("features", []) if gj else []):
        geom = f.get("geometry", {}).get("type")
        p = f.get("properties", {})
        if geom == "Point":
            nodes[p.get("node_id")] = {"tls": bool(p.get("tls_id"))}
        elif geom == "LineString":
            edges.append({"id": p.get("edge_id"),
                          "from": p.get("from_node"), "to": p.get("to_node"),
                          "lanes": p.get("lanes", 1),
                          "speed": round(p.get("speed_limit", 0) or 0, 2)})
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["from"]] = degree.get(e["from"], 0) + 1
        degree[e["to"]] = degree.get(e["to"], 0) + 1
    key_inters = sorted(k for k, d in degree.items() if d >= 4)
    # 主干道：路网自身的最高限速档。雄安窄路密网限速为 30~50 km/h，
    # 固定 60 km/h 阈值会恒为空，故按实测最高限速取档。
    top_speed = max((e["speed"] for e in edges), default=0.0)
    arterial = [e["id"] for e in edges if e["speed"] >= top_speed - 0.01]
    graph: dict[str, list[str]] = {}
    if eng is not None:
        try:
            for e in edges:
                graph[e["id"]] = list(eng.get_edge_successors(e["id"]))
        except Exception:  # noqa: BLE001
            graph = {}
    tls_ids: list[str] = []
    if eng is not None:
        try:
            tls_ids = sorted(eng.get_tls_ids())
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "data": {
        "intersection_count": len(nodes),
        "edge_count": len(edges),
        "key_intersections": key_inters[:40],      # 度 ≥ 4 的路口
        "tls_ids": tls_ids[:40],
        "arterial_speed_limit": round(top_speed, 2),  # 主干道限速档（m/s）
        "arterial_edges": arterial[:60],           # 主干道（最快限速档）
        "edge_graph": graph,                        # 边 → 后继边（可达关系）
        "edges": [{"id": e["id"], "from": e["from"], "to": e["to"],
                   "lanes": e["lanes"], "speed": e["speed"]} for e in edges][:200],
    }}


def _tool_region_status(eng, edges: list) -> dict:
    """区域聚合指标：车辆数/平均速度/排队/拥堵度。"""
    if eng is None:
        return {"ok": False, "message": "仿真未启动"}
    if not edges:
        try:
            edges = [e for e in eng.get_edge_ids() if not e.startswith(":")]
        except Exception:  # noqa: BLE001
            edges = []
    total_v, speeds, queued = 0, [], 0
    for eid in list(edges)[:80]:
        try:
            st = eng.get_edge_stats(eid)
            total_v += st["vehicle_count"]
            if st["mean_speed"] > 0:
                speeds.append(st["mean_speed"])
            queued += eng.get_edge_queue(eid)
        except Exception:  # noqa: BLE001
            continue
    avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 0.0
    congestion = round(min(1.0, queued / max(1, total_v)), 3)
    return {"ok": True, "data": {
        "edge_count": len(edges),
        "vehicle_count": total_v,
        "avg_speed": avg_speed,
        "queued_vehicles": queued,
        "congestion": congestion,
    }}


def _tool_configure_algorithm(runtime, args) -> dict:
    """设置标准化算法参数（对接 /algorithms 契约，含护栏校验）。"""
    from app.algorithms.adapter import get_adapter
    aid = str(args.get("algorithm_id", ""))
    try:
        adapter = get_adapter(runtime, aid)
    except KeyError:
        return {"ok": False, "message": f"算法不存在: {aid}"}
    params = args.get("params") or {}
    if not isinstance(params, dict):
        return {"ok": False, "message": "params 需为对象"}
    if not adapter.spec or not adapter.spec.params:
        return {"ok": False, "message": f"算法 {aid} 未声明可配置参数"}
    res = adapter.config(params)
    if not res.get("ok"):
        return {"ok": False, "message": res.get("message", "配置失败")}
    return {"ok": True, "data": {
        "algorithm_id": aid,
        "applied": res.get("applied", []),
        "params": res.get("params", {}),
        "active": res.get("active", True),   # False=仅写入待生效配置，尚未生效
        "note": res.get("note"),
    }}


def _tool_algorithm_action(runtime, args) -> dict:
    """调用标准化算法通用动作。"""
    from app.algorithms.adapter import get_adapter
    aid = str(args.get("algorithm_id", ""))
    action = str(args.get("action", ""))
    try:
        adapter = get_adapter(runtime, aid)
    except KeyError:
        return {"ok": False, "message": f"算法不存在: {aid}"}
    return adapter.action(action, args.get("params") or {})


def _current_metrics(runtime) -> dict:
    """当前全局指标快照（供对比基线）。"""
    out: dict = {}
    try:
        ov = runtime.realtime_metrics().get("overall", {})
        out["vehicle_count"] = ov.get("vehicle_count", 0)
        out["avg_speed"] = round(ov.get("avg_speed", 0) or 0, 3)
        out["avg_waiting_time"] = round(ov.get("avg_waiting_time", 0) or 0, 3)
        out["avg_queue_length"] = round(ov.get("avg_queue_length", 0) or 0, 3)
        out["total_throughput"] = ov.get("total_throughput", 0)
    except Exception:  # noqa: BLE001
        pass
    try:
        sp = runtime.spotlight()
        out["completion_rate"] = round(sp.get("completion_rate", 0) or 0, 4)
    except Exception:  # noqa: BLE001
        pass
    return out


def _tool_algorithm_state(runtime, args) -> dict:
    """算法当前参数 + 框架统一观测 + 算法内部指标（MCP resources/read）。"""
    from app.algorithms.adapter import get_adapter
    aid = str(args.get("algorithm_id") or
              (getattr(runtime.scheme, "name", "") if runtime.scheme else ""))
    if not aid:
        return {"ok": False, "message": "未指定算法，且当前无激活方案"}
    try:
        adapter = get_adapter(runtime, aid)
    except KeyError:
        return {"ok": False, "message": f"算法不存在: {aid}"}
    try:
        return {"ok": True, "data": adapter.state()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"读取算法状态失败: {exc}"}


def _tool_compare_metrics(runtime, action: str) -> dict:
    """调控前后对比：set 记基线 / compare 返回差异（后清基线）/ clear 清除。"""
    action = action or "compare"
    if action == "set":
        runtime._agent_baseline = _current_metrics(runtime)
        return {"ok": True, "message": "已记录当前指标为基线",
                "baseline": runtime._agent_baseline}
    if action == "clear":
        runtime._agent_baseline = None
        return {"ok": True, "message": "基线已清除"}
    base = runtime._agent_baseline
    if base is None:
        runtime._agent_baseline = _current_metrics(runtime)
        return {"ok": True,
                "message": "当前无基线，已自动记录为基线（调控后再调用 compare 返回对比）",
                "baseline": runtime._agent_baseline}
    now = _current_metrics(runtime)
    diff = {}
    for k, v in now.items():
        if k in base:
            diff[k] = {"before": base[k], "after": v,
                       "delta": round(v - base[k], 3)}
    runtime._agent_baseline = None  # 对比后清除，避免陈旧基线
    return {"ok": True, "data": {"comparison": diff}}
