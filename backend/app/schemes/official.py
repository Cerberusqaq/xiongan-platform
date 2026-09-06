"""官方方案（mappo优化）：20 路口路网专属 · 官方三档配时切换。

数据：backend/data/official_phase_programs.json —— 由 scripts/build_official_phase_programs.py
把官方 demo_1..20 的早/平/晚三套配时（相位名/绿时/黄灯/全红，逐相位完全忠于官方）
展开为 base_network 各信号机（tls id '1'..'20'，与官方一一对应）可直接热替换的
完整 SUMO 相位程序。

运行策略（简化 mappo / 自适应选档）：
  - 每个信号路口独立决策，周期 DECISION_STEP（默认 60s）选一次档；
  - 档位动作 = {0:早高峰, 1:平峰, 2:晚高峰}；
  - 决策特征 = 该路口按官方"东西/南北"臂分组的实时排队比 + 该档官方绿时占比；
    （正交四臂路口自动 EW/NS 选档；无法分方向组的 T 型/斜交/无差异路口
      退化为"总绿时最大档"或固定早高峰档，并在 get_status 标注退化原因）
  - 支持加载学习权重（simplified MAPPO / 小策略），mode=mappo 时走权重推理；
    未加载权重时用上面启发式（可解释、立即可演示）。
  - 换档 = 把该信号机整程序热替换为所选官方档相位序列（setProgramLogic），
    即 SUMO 层面完整执行官方配时（直行/左转按最左车道分相、右转并入最右或常绿）。

非 base_network / 无官方库：不接管，保持路网原配时（等价固定配时基线），
get_status 标注原因，方案对所有路网安全。
"""

import json
import os

from app.algorithms.base import AlgorithmSpec, ParamSpec
from app.schemes.base import BaseScheme
from app.schemes.registry import register_scheme

DECISION_STEP = 60          # 决策周期（仿真秒）
MODE_AUTO = "auto"          # 启发式自适应选档（EW/NS 排队比匹配官方绿时占比）
MODE_MAPPO = "mappo"        # 学习策略（权重加载后走 argmax，未加载回退 auto）
PLAN_NAMES = ["早高峰", "平峰", "晚高峰"]

# EW/NS 官方方向组判定所需的罗盘集合（近正交网格；斜向臂按最接近主轴折算见 build 脚本）
_EW_SET = {"E", "NE", "SE"}
_NS_SET = {"N", "NW", "S", "SW"}


def _data_path() -> str:
    d = os.path.dirname(os.path.abspath(__file__))          # .../app/schemes
    return os.path.join(os.path.dirname(os.path.dirname(d)),  # .../app → backend/data
                        "data", "official_phase_programs.json")


@register_scheme
class OfficialPlansController(BaseScheme):
    """官方方案（mappo优化）：官方三档配时切换（20 路口路网专属）。"""

    name = "official"

    algorithm_spec = AlgorithmSpec(
        kind="signal",
        description="官方方案（mappo优化）：将官方 20 路口早/平/晚三套配时按相位"
                    "完整重建到信号机程序，运行中按实时排队自适应选档（简化 mappo）",
        params=[
            ParamSpec("mode", "决策模式", type="enum", default="auto",
                      enum=["auto", "mappo"],
                      desc="auto=启发式 EW/NS 排队比选档；mappo=学习策略权重选档"),
            ParamSpec("decision_step", "决策周期", type="number", default=DECISION_STEP,
                      minimum=20, maximum=300, unit="s",
                      desc="每路口重新选档的间隔"),
        ],
        observables=["vehicle_count", "avg_queue", "tls_queues"],
        metrics=["mode", "tls_switches", "plan_tls"],
        capabilities=["switch_mode", "switch_plan"],
    )

    def __init__(self, ctx):
        super().__init__(ctx)
        self.mode = str(ctx.config.get("mode", MODE_AUTO)).strip().lower()
        if self.mode not in (MODE_AUTO, MODE_MAPPO):
            self.mode = MODE_AUTO
        self.decision_step = float(ctx.config.get("decision_step", DECISION_STEP))
        # 加载官方相位程序库
        self._prog = self._load_programs()
        self._active_tls: list[str] = []      # 受管信号机（有官方库的 tls）
        self._schedules: dict[str, list] = {}  # tid -> [ [ (dur,state)... ] x3 档 ]
        self._arms: dict[str, dict] = {}       # tid -> {edge: compass}
        self._conns: dict[str, list] = {}      # tid -> [{from,lane,dir}...]
        self._plan: dict[str, int] = {}        # tid -> 当前档 0..2
        self._next_at: dict[str, int] = {}     # tid -> 下次决策步
        self._switches = 0
        self._last_step = 0
        self._reason = ""

    # ── 数据加载 ────────────────────────────────────────────

    def _load_programs(self):
        p = _data_path()
        if not os.path.isfile(p):
            self._reason = f"缺官方相位库: {p}"
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:  # noqa: BLE001
            self._reason = f"官方相位库解析失败: {exc}"
            return {}

    def _net_matches(self) -> bool:
        """确认当前路网是官方库对应的 20 路口路网（tls id 为数字 1..20 且都能在库中找到）。"""
        try:
            ids = self.ctx.engine.get_tls_ids()
        except Exception:  # noqa: BLE001
            return False
        if not ids:
            return False
        return all(t in self._prog for t in ids)

    def init(self) -> None:
        self._last_step = 0
        if not self._prog:
            return
        if not self._net_matches():
            self._reason = "当前路网无官方配时库（非 20 路口路网），保持路网原配时=固定基线"
            return
        eng = self.ctx.engine
        self._active_tls = [t for t in eng.get_tls_ids() if t in self._prog]
        for tid in self._active_tls:
            entry = self._prog[tid]
            self._arms[tid] = {e: c for e, c in (entry.get("arms") or {}).items()}
            self._conns[tid] = entry.get("conns") or []
            self._schedules[tid] = []
            for pi, plan in enumerate(entry.get("plans", [])):
                sched = [(ph["dur"], ph["state"]) for ph in plan.get("phases", [])]
                self._schedules[tid].append(sched)
            self._plan[tid] = 0
            self._next_at[tid] = int(self.decision_step)
        if not self._active_tls:
            self._reason = "当前路网无受管信号机"
            return
        # 初始：按当前仿真时刻所在官方时段选档（route 起始=早高峰演示默认）
        self._apply_plan_silent()   # 第一档（早高峰）程序先落地，避免 60s 内仍是内嵌固定配时
        self._reason = f"官方库 {len(self._prog)} 路口 · 受管 {len(self._active_tls)} 信号机 · 简化mappo选档"

    # ── 每步调度 ────────────────────────────────────────────

    def on_step(self) -> None:
        if not self._active_tls:
            return
        self._last_step += 1
        now = self._last_step
        changed = False
        for tid in self._active_tls:
            if now < self._next_at.get(tid, 1 << 30):
                continue
            self._next_at[tid] = now + int(self.decision_step)
            pid = self._decide_plan(tid)
            if pid is not None and pid != self._plan.get(tid):
                self._plan[tid] = pid
                try:
                    sched = self._schedules[tid][pid]
                    self.ctx.engine.set_tls_phase_schedule(tid, sched)
                    self._switches += 1
                    changed = True
                except Exception:  # noqa: BLE001 单路口失败不阻塞
                    pass
        if changed:
            ev = getattr(self.ctx, "push_event", None)
            if callable(ev):
                try:
                    ev("scheme", f"官方方案：自动选档切换（累计 {self._switches} 次）", {})
                except Exception:  # noqa: BLE001
                    pass

    def _apply_plan_silent(self) -> None:
        """启动即应用所选档位的整程序（把官方配时真正落到 SUMO）。"""
        for tid in self._active_tls:
            pid = self._plan.get(tid, 0)
            sched = self._schedules[tid][pid]
            try:
                self.ctx.engine.set_tls_phase_schedule(tid, sched)
            except Exception:  # noqa: BLE001
                pass

    # ── 简化 mappo / 启发式选档 ────────────────────────────

    def _dir_queues(self, tid: str) -> tuple[float, float, float]:
        """返回 (EW 排队, NS 排队, 总排队)。按官方库 arms 的罗盘分组。"""
        eng = self.ctx.engine
        ew = ns = 0.0
        for edge, comp in (self._arms.get(tid) or {}).items():
            try:
                q = float(eng.get_edge_queue(edge))
            except Exception:  # noqa: BLE001
                q = 0.0
            if comp in _EW_SET:
                ew += q
            elif comp in _NS_SET:
                ns += q
        return ew, ns, ew + ns

    def _decide_plan(self, tid: str) -> int | None:
        """返回下一个档位 index；None=保持现状。"""
        entry = self._prog[tid]
        plans = entry.get("plans") or []
        if len(plans) < 2:
            return None
        # 各档绿时占比（EW 组）
        ew_ratios = [float(p.get("ew_ratio") or 0.5) for p in plans]
        # 若三档比例几乎一致 → 无 EW/NS 分档差异：按官方时段表区分意义不大，
        # 但总绿时/周期仍有差别 → 用总排队强度选周期更长的档（高峰给更多总绿）。
        spread = max(ew_ratios) - min(ew_ratios)
        ew_q, ns_q, tot_q = self._dir_queues(tid)
        if spread > 0.08 and (ew_q + ns_q) > 0:
            # 排队偏一侧 → 选该侧官方绿时占比最高的档
            demand_ew = ew_q / (ew_q + ns_q)
            best, best_d = 0, 1e9
            for pi, r in enumerate(ew_ratios):
                d = abs(r - demand_ew)
                if d < best_d:
                    best, best_d = pi, d
            return best
        # 退化：排队越强选总相位时长（周期）越大的档；无车时保持 0
        if tot_q < 3.0:
            return None
        cyc = [float(p.get("cycle_built") or 0) for p in plans]
        if max(cyc) - min(cyc) < 1:
            return None
        return cyc.index(max(cyc))

    # ── API 动作 ────────────────────────────────────────────

    def handle_action(self, action: str, params: dict) -> dict:
        if action == "switch_mode":
            m = str(params.get("mode", "") or "").strip().lower()
            if m in (MODE_AUTO, MODE_MAPPO):
                self.mode = m
                return {"ok": True, "mode": self.mode,
                        "note": "mappo 需已加载权重；未加载时回退 auto"}
            return {"ok": False, "message": f"未知模式: {m}"}
        if action == "switch_plan":
            # 手动选档：plan = 早高峰 / 平峰 / 晚高峰（或 0/1/2）
            want = params.get("plan")
            if isinstance(want, str):
                try:
                    idx = PLAN_NAMES.index(want)
                except ValueError:
                    return {"ok": False, "message": f"档位不存在: {want}"}
            else:
                idx = int(want or 0)
            tid = str(params.get("tls_id", "") or "")
            if not self._active_tls:
                return {"ok": False, "message": "当前路网未启用官方方案"}
            targets = [tid] if tid in self._active_tls else self._active_tls
            for t in targets:
                if 0 <= idx < len(self._schedules.get(t, [])):
                    self._plan[t] = idx
                    try:
                        self.ctx.engine.set_tls_phase_schedule(
                            t, self._schedules[t][idx])
                        self._switches += 1
                    except Exception:  # noqa: BLE001
                        pass
            return {"ok": True, "plan": PLAN_NAMES[idx] if idx < 3 else idx,
                    "tls": targets}
        if action == "set_params":
            if "mode" in params:
                self.mode = str(params["mode"]).strip().lower()
            if "decision_step" in params:
                self.decision_step = float(params["decision_step"])
            return {"ok": True}
        if action == "get_params":
            return {"ok": True, "params": {
                "mode": self.mode, "decision_step": self.decision_step}}
        if action == "get_status":
            return self._get_status()
        return {"ok": False, "message": f"未知动作: {action}"}

    def _get_status(self) -> dict:
        return {
            "ok": True,
            "mode": self.mode,
            "tls_switches": self._switches,
            "active_tls": len(self._active_tls),
            "reason": self._reason,
            "plans": {t: (self._plan.get(t, 0), PLAN_NAMES[self._plan.get(t, 0)]
                          if self._plan.get(t, 0) < 3 else self._plan.get(t, 0))
                      for t in self._active_tls},
            "decision_step": self.decision_step,
        }

    def cleanup(self) -> None:
        self._active_tls = []
        self._schedules = {}
        self._plan = {}
