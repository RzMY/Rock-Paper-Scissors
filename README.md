# Rock-Paper-Scissors YOLO

基于 YOLOv8n 的实时手势识别猜拳游戏。通过摄像头捕捉手势，用目标检测模型实时识别「石头 / 布 / 剪刀」，并与一个会**学习你出拳习惯**的集成 AI 对手实时对战。

后端使用 FastAPI 提供 REST + WebSocket 接口，前端是无框架的原生 JavaScript，对局数据持久化在 SQLite 中。

## 功能特性

- **实时手势检测**：浏览器以 ~15fps 采集摄像头画面，经 WebSocket 送到后端做 YOLO 推理，返回带标注框的画面。
- **自适应 AI 对手**：三种预测策略组成集成模型，由元学习器（meta-learner）根据近期准确率动态选择最优策略，越打越懂你。
- **完整对局状态机**：等待 → 倒计时 → 出拳 → 结算，支持手动单局和自动连打两种模式。
- **可视化统计面板**：胜率仪表盘、胜负平记录、出拳分布、各 AI 策略实时准确率、历史对局表。
- **AI 决策透明化**：前端「AI Console」实时展示每回合各策略的预测、被选中的策略及其准确率。
- **数据持久化**：每一回合都写入 SQLite，可随时查询统计与历史。

## 技术栈

| 层 | 技术 |
|---|---|
| 模型 | YOLOv8n (Ultralytics) + PyTorch |
| 后端 | FastAPI + Uvicorn + WebSocket |
| 推理 / 图像 | OpenCV + NumPy |
| 存储 | SQLite (WAL 模式) |
| 前端 | 原生 HTML / CSS / JavaScript（无框架）|
| 数据处理 | scikit-learn（分层划分）|

## 目录结构

```
Rock-Paper-Scissors/
├── scripts/
│   ├── prepare_data.py    # Roboflow Pascal VOC CSV → YOLO txt 格式，切分 train/val/test
│   ├── train.py           # 训练 YOLOv8n，最优权重复制到 models/rps_yolov8n.pt
│   └── generate_doc.py    # 生成 Word 项目文档（docs/）
├── backend/
│   ├── app.py             # FastAPI 服务：REST 接口 + /ws 游戏主循环
│   ├── config.py          # 全部可调常量（路径、计时、置信度阈值、AI 参数）
│   ├── model.py           # YOLOInference 封装（predict / get_best_move）+ 画框标注
│   ├── game_engine.py     # 游戏状态机、回合结算、计分
│   ├── ai_strategy.py     # 集成 AI 对手（Markov / Frequency / AntiRotator / Meta）
│   ├── database.py        # SQLite 读写（rounds 表），导入时自动建表
│   └── static/            # 原生 JS 前端
├── data.yaml              # YOLO 数据集配置（路径 + 3 个类别）
├── models/                # 训练产出的 .pt 权重（不纳入版本控制）
└── requirements.txt       # Python 依赖
```

## 快速开始

### 1. 环境准备

```bash
pip install -r requirements.txt
```

> 建议使用 Python 3.10+ 与独立虚拟环境。如需 GPU 训练/推理，请按官方指引安装对应 CUDA 版本的 PyTorch。

### 2. 准备数据集

将 Roboflow 导出的 Pascal VOC CSV 格式数据集放入 `datasets/`（含 `train/` 与 `test/` 及各自的 `_annotations.csv`），然后运行：

```bash
python scripts/prepare_data.py
```

该脚本会把标注转换为 YOLO txt 格式，按 80/20 分层切分出验证集，并生成 `data.yaml`。

### 3. 训练模型

```bash
# 正式训练（GPU）
python scripts/train.py --epochs 100 --batch 64 --device cuda

# CPU 训练
python scripts/train.py --epochs 10 --batch 4 --device cpu
```

训练完成后，最优权重会被复制到 `models/rps_yolov8n.pt`——这正是服务端默认加载的路径。

### 4. 启动游戏

```bash
# 方式一：直接运行（带热重载）
python backend/app.py

# 方式二：uvicorn
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 <http://localhost:8000>，允许摄像头权限即可开始。

> 若 `models/rps_yolov8n.pt` 不存在，服务仍会启动，但检测功能关闭，前端会提示 "Model not loaded"，需先完成训练。

## 玩法说明

- **Start Round** 按钮或 <kbd>Space</kbd>：开始一局，进入 3 秒倒计时。
- 倒计时结束进入「出拳」，把手势清晰地展示给摄像头，模型会取置信度最高的检测作为你的出拳。
- **Auto** 按钮或 <kbd>A</kbd>：切换自动连打模式，每局结算后自动开始下一局。
- **Reset All**：清空所有比分与历史记录。

## AI 对手原理

AI 的目标是**预测你的下一手**，然后出能克制它的一手。它由三个预测器 + 一个元学习器组成（见 `backend/ai_strategy.py`）：

| 策略 | 原理 |
|---|---|
| **MarkovChainPredictor** | 基于历史出拳的 N-gram（order=3）模式匹配，预测下一手 |
| **FrequencyAnalyzer** | 指数衰减（decay=0.85）的加权频率统计，偏好近期高频手势 |
| **AntiRotator** | 检测「石头→布→剪刀」这类循环出拳规律 |
| **MetaStrategy** | 追踪各预测器近 20 局的准确率并选出最佳；前 30 局有 20% 概率随机探索，避免过早收敛 |

每回合会对**所有**候选策略计分（不只被选中的那个），因此统计面板能同时展示各策略的真实命中率。

## 游戏状态机

```
WAITING ──start_round──▶ COUNTDOWN ──(3s tick)──▶ SHOOT ──检测到出拳──▶ RESULT ──(2s)──▶ WAITING
                                                                                    └─(auto 模式则自动开始下一局)
```

状态推进由 WebSocket 上的 `tick_loop` 定时驱动（每 0.1s 一次）。

## REST 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（含模型是否加载、当前状态）|
| GET | `/api/stats` | 汇总统计（胜负平、胜率、出拳分布、策略准确率、比分）|
| GET | `/api/history?limit=20` | 最近若干回合记录 |
| GET | `/api/state` | 当前游戏状态与比分 |
| POST | `/api/reset` | 重置比分与历史 |

实时对局通过单个 WebSocket 端点 `/ws` 完成，消息类型包括 `frame`、`start_round`、`toggle_auto`、`reset`、`get_state`、`get_stats`。

## 关键配置

集中在 `backend/config.py`：

- `CONFIDENCE_THRESHOLD = 0.3`：YOLO 检测的最小置信度
- `COUNTDOWN_SECONDS = 3` / `RESULT_DISPLAY_SECONDS = 2`：倒计时与结算展示时长
- `MARKOV_ORDER = 3` / `FREQUENCY_DECAY = 0.85` / `META_WINDOW = 20`：AI 参数
- `WS_FRAME_QUALITY = 85`：WebSocket 回传标注帧的 JPEG 质量

## 生成项目文档

```bash
python scripts/generate_doc.py
```

会在 `docs/` 下生成一份完整的 Word 项目文档（依赖 `python-docx`，已包含在 `requirements.txt`）。

## 数据集类别

模型识别 3 个类别（见 `data.yaml`）：

| id | 类别 |
|---|---|
| 0 | Rock（石头）|
| 1 | Paper（布）|
| 2 | Scissors（剪刀）|
