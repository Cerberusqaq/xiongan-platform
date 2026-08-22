"""TraCI 引擎适配器：封装 SUMO 读写接口，全部模块共用此契约。"""

import os

import traci


class EngineError(Exception):
    """引擎异常。code 对应 requirements 文档错误码：1001 未连接、1002 对象不存在。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Engine:
    """对 SUMO/TraCI 的薄封装，方法签名即全项目共享契约。"""

    def __init__(self):
        self._connected = False
        self._step = 0
        self._net_file = ""
        self._route_files: list[str] = []
        self._graph: dict | None = None
        self._tls_phase_cache: dict[str, int] = {}
        self._tls_links_cache: dict[str, list] = {}
        self._cum_arrivals = 0
        self._cum_departed = 0
        self._edge_length_cache: dict[str, float] = {}
        self._edge_speed_cache: dict[str, float] = {}

    # ── 生命周期 ────────────────────────────────────────────

    def connect(self, net_file: str, route_files: list[str] | None = None,
                add_files: list[str] | None = None, begin: int = 0,
                end: int = 86400, step_length: float = 1.0) -> None:
        sumo_home = os.environ.get("SUMO_HOME", "")
        sumo_bin = os.path.join(sumo_home, "bin", "sumo.exe") if sumo_home else "sumo"
        if not os.path.exists(sumo_bin):
            sumo_bin = "sumo"
        cmd = [sumo_bin, "-n", net_file, "-b", str(begin), "-e", str(end),
               "--step-length", str(step_length), "--no-step-log", "--quit-on-end"]
        for rf in route_files or []:
            cmd += ["-r", rf]
        for af in add_files or []:
            cmd += ["-a", af]
        try:
            traci.start(cmd)
        except Exception as exc:  # noqa: BLE001 统一转成 EngineError 上报
            raise EngineError(1006, f"仿真启动失败: {exc}") from exc
        self._connected = True
        self._net_file = net_file
        self._route_files = route_files or []
        self._step = 0

    def close(self) -> None:
        if self._connected:
            try:
                traci.close()
            except Exception:  # noqa: BLE001 关闭失败不阻塞
                pass
        self._connected = False

    def step(self) -> int:
        self._require_connected()
        traci.simulationStep()
        self._step += 1
        return self._step

    def get_sim_time(self) -> float:
        self._require_connected()
        return float(traci.simulation.getTime())

    def net_file(self) -> str:
        return self._net_file

    # ── 读取类 ──────────────────────────────────────────────

    def get_edge_ids(self) -> list[str]:
        self._require_connected()
        return list(traci.edge.getIDList())

    def get_edge_stats(self, edge_id: str) -> dict:
        self._require_connected()
        try:
            return {
                "vehicle_count": int(traci.edge.getLastStepVehicleNumber(edge_id)),
                "mean_speed": float(traci.edge.getLastStepMeanSpeed(edge_id)),
                "occupancy": float(traci.edge.getLastStepOccupancy(edge_id)),
                "travel_time": float(traci.edge.getTraveltime(edge_id)),
            }
        except traci.TraCIException:
            return {"vehicle_count": 0, "mean_speed": 0.0, "occupancy": 0.0,
                    "travel_time": float("inf")}

    def get_edge_queue(self, edge_id: str) -> int:
        """该边当前车辆数（轻量，1 次 TraCI 调用）。"""
        self._require_connected()
        try:
            return int(traci.edge.getLastStepVehicleNumber(edge_id))
        except traci.TraCIException:
            return 0

    def get_vehicle_ids(self) -> list[str]:
        self._require_connected()
        return list(traci.vehicle.getIDList())

    def get_vehicle_state(self, veh_id: str) -> dict:
        self._require_connected()
        try:
            x, y = traci.vehicle.getPosition(veh_id)
            return {
                "x": float(x), "y": float(y),
                "angle": float(traci.vehicle.getAngle(veh_id)),
                "speed": float(traci.vehicle.getSpeed(veh_id)),
                "lane": traci.vehicle.getLaneID(veh_id),
                "type": traci.vehicle.getTypeID(veh_id),
                "route": list(traci.vehicle.getRoute(veh_id)),
                "waiting_time": float(traci.vehicle.getWaitingTime(veh_id)),
            }
        except traci.TraCIException as exc:
            raise EngineError(1002, f"车辆不存在: {veh_id}") from exc

    def get_departed_vehicles(self) -> list[str]:
        self._require_connected()
        return list(traci.simulation.getDepartedIDList())

    def get_arrived_vehicles(self) -> list[str]:
        self._require_connected()
        return list(traci.simulation.getArrivedIDList())

    def get_longest_travel_vehicle(self) -> dict | None:
        """在线行驶时间最长的车辆（当前时间 - depart 时间）。"""
        self._require_connected()
        now = float(traci.simulation.getTime())
        best, best_id = -1.0, None
        for vid in self.get_vehicle_ids():
            try:
                t = now - float(traci.vehicle.getDeparture(vid))
            except traci.TraCIException:
                continue
            if t > best:
                best, best_id = t, vid
        if best_id is None:
            return None
        st = self.get_vehicle_state(best_id)
        return {"id": best_id, "duration": round(best, 1),
                "waiting_time": round(st["waiting_time"], 1),
                "x": st["x"], "y": st["y"], "speed": round(st["speed"], 2)}

    def get_longest_wait_vehicle(self) -> dict | None:
        """累计等待时间最长的车辆。"""
        self._require_connected()
        best, best_id = -1.0, None
        for vid in self.get_vehicle_ids():
            try:
                w = float(traci.vehicle.getWaitingTime(vid))
            except traci.TraCIException:
                continue
            if w > best:
                best, best_id = w, vid
        if best_id is None:
            return None
        st = self.get_vehicle_state(best_id)
        return {"id": best_id, "waiting_time": round(best, 1),
                "x": st["x"], "y": st["y"], "speed": round(st["speed"], 2)}

    def get_most_congested_edge(self) -> dict | None:
        """排队车辆最多的道路（排除 SUMO 内部连接边 :xxx）。"""
        self._require_connected()
        best, best_id = -1, None
        for eid in self.get_edge_ids():
            if eid.startswith(":"):
                continue
            q = self.get_edge_queue(eid)
            if q > best:
                best, best_id = q, eid
        if best_id is None:
            return None
        st = self.get_edge_stats(best_id)
        return {"id": best_id, "queue": best,
                "mean_speed": round(st["mean_speed"], 2),
                "occupancy": round(st["occupancy"], 4)}

    def get_cumulative_arrivals(self) -> int:
        """累计到达车辆数（getArrivedNumber 是每步增量，需自行累加）。"""
        self._require_connected()
        self._cum_arrivals += int(traci.simulation.getArrivedNumber())
        return self._cum_arrivals

    def get_cumulative_departed(self) -> int:
        """累计出发车辆数（用于完成率 = 到达/出发）。"""
        self._require_connected()
        self._cum_departed += int(traci.simulation.getDepartedNumber())
        return self._cum_departed

    def get_edge_speed_limit(self, edge_id: str) -> float:
        self._require_connected()
        if edge_id in self._edge_speed_cache:
            return self._edge_speed_cache[edge_id]
        value = 13.89
        try:
            # TraCI 无 edge 级限速接口，取该边第 0 车道限速
            value = float(traci.lane.getMaxSpeed(f"{edge_id}_0")) or 13.89
        except traci.TraCIException:
            pass
        self._edge_speed_cache[edge_id] = value
        return value

    def get_edge_length(self, edge_id: str) -> float:
        self._require_connected()
        if edge_id in self._edge_length_cache:
            return self._edge_length_cache[edge_id]
        value = 0.0
        try:
            value = float(traci.lane.getLength(f"{edge_id}_0"))
        except traci.TraCIException:
            pass
        self._edge_length_cache[edge_id] = value
        return value

    def get_edge_successors(self, edge_id: str) -> list[str]:
        """边图中 edge_id 的后继边列表（从 net.xml 经 sumolib 解析并缓存）。"""
        return self._graph_cache().get(edge_id, [])

    def get_edge_road_type(self, edge_id: str) -> str:
        limit = self.get_edge_speed_limit(edge_id)
        if limit >= 16.7:
            return "arterial"
        if limit >= 11.1:
            return "secondary"
        return "local"

    def _graph_cache(self) -> dict:
        if self._graph is None:
            self._graph = {}
            try:
                import sumolib
                net = sumolib.net.readNet(self._net_file)
                self._graph = {
                    e.getID(): [s.getID() for s in e.getToNode().getOutgoing()]
                    for e in net.getEdges()
                }
            except Exception:  # noqa: BLE001
                self._graph = {}
        return self._graph

    def get_tls_position(self, tls_id: str):
        """信号灯坐标 (x, y) 或 None（TraCI 无法取得时）。"""
        self._require_connected()
        try:
            x, y = traci.junction.getPosition(tls_id)
            return float(x), float(y)
        except traci.TraCIException:
            return None

    def get_tls_ids(self) -> list[str]:
        self._require_connected()
        return list(traci.trafficlight.getIDList())

    def get_tls_state(self, tls_id: str) -> dict:
        self._require_connected()
        try:
            return {
                "state_str": traci.trafficlight.getRedYellowGreenState(tls_id),
                "phase_index": int(traci.trafficlight.getPhase(tls_id)),
                "num_phases": self._tls_phase_count(tls_id),
                "duration": float(traci.trafficlight.getPhaseDuration(tls_id)),
                "phase_duration": float(traci.trafficlight.getPhaseDuration(tls_id)),
                "elapsed": float(traci.trafficlight.getSpentDuration(tls_id)),
            }
        except traci.TraCIException as exc:
            raise EngineError(1002, f"信号灯不存在: {tls_id}") from exc

    def get_tls_connections(self, tls_id: str) -> dict:
        """相位索引 -> 受控车道列表（简化映射，供 Webster 相位-edge 反查）。"""
        self._require_connected()
        try:
            lanes = list(traci.trafficlight.getControlledLanes(tls_id))
            n = self._tls_phase_count(tls_id)
            return {i: lanes for i in range(n)}
        except traci.TraCIException as exc:
            raise EngineError(1002, f"信号灯不存在: {tls_id}") from exc

    def get_tls_links(self, tls_id: str) -> list[dict]:
        """受控 link 列表（与 state_str 字符一一对应）：[{from_edge, from_lane}]。

        前端据此在对应进口方向绘制逐车道信号灯。静态数据，按 tls 缓存。
        """
        cached = self._tls_links_cache.get(tls_id)
        if cached is not None:
            return cached
        links: list[dict] = []
        try:
            raw = traci.trafficlight.getControlledLinks(tls_id)
            for lnk in raw:
                inner = lnk[0] if (len(lnk) == 1 and isinstance(lnk[0], tuple)) else lnk
                parts = tuple(inner)
                if not parts:
                    continue
                frm = parts[0]
                if isinstance(frm, (tuple, list)):
                    lane_id = str(frm[0])
                    lane_idx = int(frm[1]) if len(frm) > 1 and isinstance(frm[1], int) else 0
                else:
                    lane_id = str(frm)
                    lane_idx = 0
                if not lane_id:
                    continue
                # lane id 形如 "E14_1_0" → 边 "E14_1"，车道 0（从 id 尾部解析车道号）
                edge = lane_id.rpartition("_")[0]
                if lane_idx == 0 and "_" in lane_id:
                    tail = lane_id.rsplit("_", 1)[-1]
                    if tail.isdigit():
                        lane_idx = int(tail)
                if not edge:
                    continue
                links.append({"from_edge": edge, "from_lane": lane_idx})
        except traci.TraCIException:  # noqa: BLE001
            pass
        self._tls_links_cache[tls_id] = links
        return links

    def _tls_phase_count(self, tls_id: str) -> int:
        """当前信号方案的相位总数（缓存，避免高频调用昂贵定义接口）。"""
        cached = self._tls_phase_cache.get(tls_id)
        if cached is not None:
            return cached
        count = 1
        try:
            logics = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)
            if logics:
                active_id = traci.trafficlight.getProgram(tls_id)
                logic = next((lg for lg in logics if lg.programID == active_id),
                             logics[0])
                count = max(1, len(logic.phases))
        except (traci.TraCIException, AttributeError):
            pass
        self._tls_phase_cache[tls_id] = count
        return count

    # ── 写入类 ──────────────────────────────────────────────

    def set_tls_phase(self, tls_id: str, phase_index: int, duration: float) -> None:
        self._require_connected()
        try:
            traci.trafficlight.setPhase(tls_id, phase_index)
            traci.trafficlight.setPhaseDuration(tls_id, duration)
        except traci.TraCIException as exc:
            raise EngineError(1002, f"信号灯不存在: {tls_id}") from exc

    def set_tls_program(self, tls_id: str, program_id: str) -> None:
        self._require_connected()
        try:
            traci.trafficlight.setProgram(tls_id, program_id)
        except traci.TraCIException as exc:
            raise EngineError(1002, f"信号灯不存在: {tls_id}") from exc
        self._tls_phase_cache.pop(tls_id, None)

    def get_vehicle_emissions(self, veh_id: str) -> dict:
        """车辆累计排放/油耗：fuel(L), co2/co/nox(g)。"""
        self._require_connected()
        try:
            return {
                "fuel": float(traci.vehicle.getFuelConsumption(veh_id)),
                "co2": float(traci.vehicle.getCO2Emission(veh_id)),
                "co": float(traci.vehicle.getCOEmission(veh_id)),
                "nox": float(traci.vehicle.getNOxEmission(veh_id)),
            }
        except traci.TraCIException as exc:
            raise EngineError(1002, f"车辆不存在: {veh_id}") from exc

    def set_vehicle_route(self, veh_id: str, edges: list[str]) -> None:
        self._require_connected()
        try:
            traci.vehicle.setRoute(veh_id, edges)
        except traci.TraCIException as exc:
            raise EngineError(1002, f"车辆不存在: {veh_id}") from exc

    def reroute_vehicle(self, veh_id: str, with_travel_time: bool = True) -> None:
        self._require_connected()
        try:
            traci.vehicle.rerouteTraveltime(veh_id)
        except traci.TraCIException as exc:
            raise EngineError(1002, f"车辆不存在: {veh_id}") from exc

    def set_edge_speed_limit(self, edge_id: str, speed: float) -> None:
        """运行时调整某条边所有车道的限速（用于施工/事故扰动）。"""
        self._require_connected()
        try:
            n = int(traci.edge.getLaneNumber(edge_id))
            for i in range(n):
                traci.lane.setMaxSpeed(f"{edge_id}_{i}", float(speed))
        except traci.TraCIException as exc:
            raise EngineError(1002, f"边不存在: {edge_id}") from exc
        self._edge_speed_cache[edge_id] = float(speed)

    def add_vehicle_route(self, veh_id: str, route_edges: list[str],
                          depart: float = 0.0, veh_type: str | None = None) -> None:
        """按完整边路线动态注入一辆车（支持任意类型）。"""
        self._require_connected()
        try:
            route_id = f"{veh_id}_route"
            traci.route.add(route_id, list(route_edges))
            vt = veh_type or "DEFAULT_VEHTYPE"
            if vt != "DEFAULT_VEHTYPE":
                try:
                    traci.vehicletype.copy("DEFAULT_VEHTYPE", vt)
                    if vt in ("bus", "truck"):
                        traci.vehicletype.setLength(vt, 10.0)
                        traci.vehicletype.setMaxSpeed(vt, 13.89)
                        traci.vehicletype.setColor(vt, (255, 107, 107, 255) if vt == "bus"
                                                   else (177, 151, 252, 255))
                    elif vt == "bicycle":
                        traci.vehicletype.setLength(vt, 2.0)
                        traci.vehicletype.setMaxSpeed(vt, 6.0)
                        traci.vehicletype.setColor(vt, (99, 230, 190, 255))
                    elif vt == "fleet":
                        traci.vehicletype.setColor(vt, (255, 169, 77, 255))
                except traci.TraCIException:
                    pass  # 类型已存在（重复注入时）
            traci.vehicle.add(veh_id, route_id, typeID=vt, depart=float(depart))
        except traci.TraCIException as exc:
            raise EngineError(1002, f"无法添加车辆 {veh_id}: {exc}") from exc

    def add_vehicle_trip(self, veh_id: str, from_edge: str, to_edge: str,
                         depart: float = 0.0, veh_type: str | None = None) -> None:
        """动态注入一辆两点车（用于大型活动突发车流/人工加车）。"""
        self.add_vehicle_route(veh_id, [from_edge, to_edge], depart, veh_type)

    # ── 内部 ────────────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self._connected:
            raise EngineError(1001, "仿真引擎未连接")
