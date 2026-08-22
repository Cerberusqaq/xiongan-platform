claude code 创建

# 车路云一体化协同管控算法与仿真平台

> 面向雄安新区"城市大脑"的车路云一体化协同管控仿真平台（赛题 XH-202613）。基于 SUMO 微观仿真，实现三套调度方案（云端集中协调 / 边缘路口自适应 / 车端路线引导），支持实时可视化、V2X 通信模拟与扰动事件注入。

## 功能

- **仿真底座**：TraCI 引擎适配、会话管理（独立线程）、车辆/信号灯/全局/路口指标增量采集、WebSocket 实时推送、GeoJSON 路网导出
- **方案一 · 分时多算法切换（云端）**：TOD 时段调度 + Webster 最优配时 + MAXBAND 绿波协调
- **方案二 · 实时观测自适应（边缘）**：SCOOT 规则自适应控制器（本地实时控制）+ STGCN 交通流预测 + **MAPPO 强化学习（已修复训练坍缩并通过验收，见 `MAPPO训练与验证指南.md`）**；MAPPO 采用 actuated"保持/推进"动作 + 真实变灯倒计时/黄红过渡，贪心推理在 routes_clean700 上 **veh=49 / speed=1.77 / wait=45s，优于 SCOOT（63.5/1.71/60）**
- **方案三 · 受限车队路线引导（车端）**：动态 Dijkstra + K-短路 + 负载均衡，公交/网约车等车队管理
- **赛题增量**：V2X 通信模拟（延迟/丢包）、扰动事件注入（施工占道/突发车流/事故）、燃油排放指标、标准化算法插件接口
- **部署**：Docker 容器化、一键启动、mock 引擎单元测试（不依赖 SUMO）

## 技术栈

| 层 | 选型 |
|---|---|
| 仿真引擎 | SUMO ≥1.18 + TraCI |
| 后端 | Python 3.10 + FastAPI + uvicorn + Pydantic v2 |
| AI | PyTorch（MAPPO / STGCN，可选） |
| 测试 | pytest + mock 引擎 |
| 部署 | Docker + docker-compose |
| 前端（他人负责，仅规范） | Vue3 + MapLibre GL + deck.gl + ECharts |

## 快速开始

```bash
cd backend
pip install -r requirements.txt          # 基础依赖
pip install -r requirements-ml.txt       # 可选：训练用 PyTorch
python -m pytest tests/                  # 运行单元测试（mock 引擎）
python -m uvicorn app.main:app --port 8000   # 启动后端
# 浏览器打开 http://127.0.0.1:8000/docs 查看接口
```

或双击 `start.bat`。

### 模型训练（单独窗口，CPU 限流默认 60%，支持断点续训）

```bash
cd backend
# 1. 全量训练（默认路网自动指向本包 networks/network/，5 场景轮换；约 30 分钟）
python scripts/train_mappo_multi.py --rounds 8 --steps 4000 \
    --out models/weights/mappo_act_full --eps0 0.3 --update-interval 200 \
    --entropy 0.4 --entropy-min 0.02 --cpu-ratio 0.6
# 2. 验证（固定配时 / SCOOT / MAPPO 贪心三行对比）
python scripts/verify_model.py --prefix models/weights/mappo_act_full --steps 2200
# 3. 换路网训练（路网无关：--net/--routes/--add 参数化，详见 docs/MAPPO训练与验证指南.md）
python scripts/train_mappo_multi.py --net D:/net/road.net.xml \
    --routes D:/net/r1.rou.xml D:/net/r2.rou.xml --out models/weights/netA \
    --rounds 8 --steps 4000 --cpu-ratio 0.6
```

## 目录结构

```
车路云协同管控平台/
├── backend/
│   ├── app/
│   │   ├── api/        # REST /api/v1 路由
│   │   ├── ws/         # WebSocket 推送
│   │   ├── core/       # 引擎适配/会话/采集/GeoJSON/runtime
│   │   ├── schemes/    # 三套调度方案 + 算法基类 + 插件注册
│   │   ├── comms/      # V2X 通信模拟
│   │   ├── events/     # 扰动事件注入
│   │   ├── metrics/    # 指标历史存储
│   │   └── models/     # 训练脚本 + 模型
│   ├── tests/          # 单元测试（mock 引擎）
│   └── Dockerfile  docker-compose.yml  requirements*.txt
├── frontend/README.md  # 前端技术选型规范
└── docs/               # 交付文档（架构/接口/评估/演示/报告）
```

## 文档

| 文档 | 内容 |
|---|---|
| `docs/云边端架构.md` | 车-路-云数据流向、三端职责、通信协议 |
| `docs/接口文档.md` | REST/WebSocket 接口、错误码、字段说明 |
| `docs/实验评估报告.md` | 基线对比、多场景多参数评估模板 + MAPPO 实测验收数据 |
| `docs/演示方案.md` | 演示场景、脚本、视频分镜 |
| `docs/系统设计与算法报告.md` | 答辩报告大纲（含 MAPPO 修复后方案二描述） |
| `docs/MAPPO训练与验证指南.md` | **MAPPO 训练/验证/换路网通用流程（本次更新核心）** |

## Skills 使用清单

- `brainstorming` — 需求澄清与设计
- `writing-plans` — 实施计划
- `executing-plans` — 计划执行
- `test-driven-development` — 测试驱动开发
- `systematic-debugging` — 系统性调试
- `verification-before-completion` — 完成前验证
