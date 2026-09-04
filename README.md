# 车路云协同管控平台（雄安 · 城市大脑）

XH-202613 竞赛赛道 C（AI 应用型）项目：以 **SUMO 微观交通仿真**为底座、**MAPPO 强化学习 + 标准化信号控制算法**为核心、**LLM 智能体**为交互入口的车路云协同管控平台。

平台同时内置了**评估报告导出**（Markdown / Word / PDF）、**标准化算法接口**（MCP 风格，算法可插拔）与**路网级 Agent 规划能力**。

---

## 一、目录结构

```
xiongan_v5/
├── start.bat               # Windows 一键启动（后端 + 前端）
├── frontend/               # Vue 3 + Vite 前端（端口 5173）
├── backend/                # FastAPI 后端（端口 8000）
│   ├── app/
│   │   ├── api/            # REST + WebSocket 接口层
│   │   ├── core/           # 引擎适配(TraCI) / 会话 / 数据采集 / 运行时
│   │   ├── schemes/        # 控制算法：方案一(配时+绿波) / 二(MAPPO·SCOOT) / 三(车端引导)
│   │   ├── algorithms/     # 标准化算法接口（MCP-like 契约）
│   │   ├── agent/          # LLM 智能体（工具调用 + 会话记忆）
│   │   ├── report/         # 评估报告生成（md/docx/pdf + matplotlib 图表）
│   │   ├── eval/           # 老评价平台评分公式移植
│   │   ├── events/         # 扰动事件注入（事故/施工/突发车流）
│   │   ├── metrics/        # 历史指标存储
│   │   ├── ws/             # WebSocket 推送
│   │   └── main.py         # 应用入口
│   ├── models/weights/     # MAPPO 训练权重（ONNX）
│   ├── data/networks/      # 训练/评估随机路网
│   └── .env                # LLM 配置（智谱免费 API / Ollama）
├── networks/network/       # SUMO 路网（base_network + 车流文件）
├── evaluator/              # 老评价平台（离线评分）
├── docs/                   # 全技术栈说明 + 各模块设计文档
└── requirements/           # 赛题与需求
```

## 二、环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Windows | 10/11 | 已适配 |
| Python | 3.14（3.10+ 均可） | 后端 |
| Node.js | 18+ | 前端构建 |
| SUMO | 1.20+（测试用 1.27.1） | 交通仿真引擎，需 `SUMO_HOME` 环境变量指向安装目录 |
| Ollama | 可选 | 本地离线 LLM（qwen2.5:3b 等） |
| PyTorch | CPU 版即可 | MAPPO 推理（无 GPU 也可运行，自动降级 SCOOT） |

后端 Python 依赖见 `backend/requirements.txt`，前端依赖随包已含 `node_modules`。

## 三、快速开始

### 方式一：一键启动（推荐）

双击 `start.bat`：
1. 自动检查并安装 Python 依赖（清华镜像）；
2. 自动检查并安装前端依赖（已有 node_modules 则跳过）；
3. 分别弹出两个窗口：后端（端口 8000）+ 前端（端口 5173）；
4. 自动打开浏览器 `http://localhost:5173`。

### 方式二：手动启动

```bat
:: 后端
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

:: 前端（另开一个终端）
cd frontend
npm run dev
```

## 四、使用说明

1. **选择路网**：顶部左侧下拉选择内置路网（悬停可预览），可上传自定义 SUMO 路网（`.net.xml` + `.rou.xml` + `.add.xml`）；
2. **启动仿真**：选择控制方案后点击"启动仿真"：
   - 基线 · 固定配时（`none`）
   - 方案一 · 固定配时+绿波（`scheme_1`，TOD + Webster + MAXBAND）
   - 方案二 · MAPPO/SCOOT（`scheme_2`，AI 实时控制，无 PyTorch 自动降级 SCOOT）
   - 方案三 · 车端引导（`scheme_3`，受限车队动态重路由）
3. **交互**：
   - 画布：滚轮缩放、拖拽平移、双击复位、点击车辆/道路/路口查看详情，可在道路上添加车流；
   - 左侧：实时指标（可勾选自定义指标，如完成率、最堵塞道路/路口，点击卡片定位到画布）、方案控制、事件注入（事故/施工/突发车流）、人工加车；
   - 右侧：**LLM 智能体**——自然语言指挥路网（可切换免费模型 glm-4-flash / glm-4.7-flash），支持查看全部工具（工具详情）、清空会话记忆；
   - 底部：实时速度曲线、离线评估对比、综合评分（老评价平台公式）、**生成报告**（md/docx/pdf，含 matplotlib 图表）；
   - 设置：深浅主题、普通/专业模式、左栏堆叠/单栏切换、各类显示开关。
4. **LLM 配置**：`backend/.env` 中 `LLM_PROVIDER=zhipu`（智谱免费 API）或 `ollama`（本地离线）。智谱密钥已随包配置（免费额度）。

## 五、常见问题

| 现象 | 处理 |
| --- | --- |
| 后端报 `SUMO_HOME` 未设置 | 安装 SUMO 后设置环境变量 `SUMO_HOME` 指向安装目录（如 `E:\`） |
| 启动仿真后无车辆 | 检查是否选择了带车流的路网（内置路网均自带） |
| 智能体回复"LLM 调用失败" | 检查 `.env` 的 `LLM_API_KEY`；智谱模型可能临时限流，切换另一模型 |
| 端口被占用 | 关闭占用进程或修改 `start.bat` 中的端口 |
| 评分显示"硬性筛选未通过" | 属于正常保护机制：拥堵严重（LOS F/完成率<60%/等待>4周期）时不评分 |

## 六、文档索引（docs/，赛事提交材料）

| 文档 | 内容 | 对应赛题交付 |
| --- | --- | --- |
| 系统设计与算法报告.md | 总体方案、算法原理、云边端、创新点、路网接入规范（附录E） | 提交① |
| 实验评估报告.md | 对比实验、图表、AI 训练方法（附录） | 提交③ |
| 接口文档.md | REST/WS 全端点、错误码、OpenAPI 导入、云-边-端数据流（§15） | 功能一任务1 |
| 部署运行说明.md | Windows/Docker 运行、自检、使用快速参考（附录） | 提交②配套 |
| 四典型路口最优调度方案.md | 单路口案例最优配时与验证 | 功能一任务2 |
| 演示方案.md | 实际场景演示与视频脚本 | 提交④ |
| pdf/ | 上述主要报告的 PDF 导出 | 提交 |

## 七、技术栈速览

前端：Vue 3 + Vite + Pinia + ECharts + Canvas 2D（自绘路网渲染）
后端：FastAPI + WebSocket + TraCI（SUMO）+ PyTorch/MAPPO + ONNX + OpenAI 兼容 LLM 客户端
算法：Webster 配时 / MAXBAND 绿波 / MAPPO（CTCE+GAE+PPO）/ SCOOT / 动态 Dijkstra 车端引导
报告：matplotlib + python-docx + reportlab

---
*本项目仅供学习与竞赛演示使用。*
