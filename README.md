# 洛克王国世界 AI 助手 (MFAAvalonia)

洛克王国世界游戏的 AI 自动化助手，基于 MFAAvalonia 框架，支持智能战斗、RAG 知识库、知识图谱可视化等功能。

## 项目概述

本项目是一个完整的洛克王国世界游戏 AI 助手，提供以下核心功能：

- **自动化战斗**: 基于 OCR 图像识别 + AI/规则 双模式决策的自动战斗系统
- **RAG 知识库**: 基于 LanceDB 的精灵和技能知识库，支持中文语义检索
- **知识图谱可视化**: Web 端实时可视化知识图谱，支持聚类浏览与实时同步
- **PVP 专家系统**: 自动分析战局并制定策略
- **多模型支持**: 集成 Gemini、Ollama、豆包、讯飞星火等多个 AI 模型
- **纯规则模式**: 无需 AI 模型，基于属性克制、能量管理、宠物切换的本地决策
- **高性能向量搜索**: 使用 `llama.cpp` 本地 GPU 加速生成语义向量 (支持 N卡 CUDA / A卡 Vulkan)

## 项目结构

```
MFAAvalonia-v2.11.8-win-x64/
├── ai_life/                         # AI 开发日志
├── config/                          # 配置文件目录
│   ├── ai_config.json               # AI 引擎配置（模型选择、API 密钥）
│   ├── pet_database_full.json       # 精灵数据库 (347 只)
│   ├── skill_database.json          # 技能数据库 (270 个)
│   ├── combat_strategy_rag.jsonl    # 战斗策略知识库
│   └── instances/default.json       # 默认实例配置
├── scripts/                         # Python 脚本工具
│   ├── rag_lancedb/                 # LanceDB 向量数据库
│   ├── sync_rag_strategies.py       # 同步策略到向量库
│   └── check_types.py               # 属性类型校验工具
├── web/                             # 知识图谱 Web 可视化
│   ├── templates/index.html         # 可视化页面
│   └── 启动知识图谱.bat             # 一键启动脚本
├── knowledge_graph_server.py        # 知识图谱 Flask 服务器
├── roco_pvp_ai.py                   # PVP AI 主脚本（核心）
├── MFAAvalonia.exe                  # MAA 主程序
└── DependencySetup_依赖库安装_win.bat  # 依赖安装脚本
```

## 核心功能详解

### 1. 双模式战斗决策

[roco_pvp_ai.py](roco_pvp_ai.py) 支持两种决策模式，通过 `config/ai_config.json` 中的 `use_ai` 切换：

#### AI 决策模式 (`use_ai: true`)
- 截图 → OCR 提取战场状态 → RAG 检索策略 → AI 模型决策 → 执行指令
- 支持多模态 VLM 和纯文本 LLM
- 结构化 JSON 输出，稳定解析

#### 纯规则模式 (`use_ai: false`)
- 零网络延迟、零 API 费用
- 属性克制优先（自动选择 2 倍克制技能）
- 能量智能管理（低能量自动恢复）
- 血量危急时自动换宠（选择克制敌方的后备精灵）

### 2. RAG 知识库

- **LanceDB 向量数据库**：精灵表 347 条、技能表 270 条
- **语义检索**：支持中文自然语言查询（如"克制火系的精灵"）
- **策略召回**：战斗时实时检索相关策略，注入 AI 提示词

### 3. 知识图谱可视化

- **Web 端可视化**：基于 vis.js 的交互式力导向图
- **节点类型**：精灵、技能、属性、策略分类
- **边类型**：克制、抵抗、免疫、技能所属、策略关联
- **实时同步**：WebSocket 推送数据变更
- **性能优化**：聚类视图 + 按需展开，支持 1000+ 节点流畅渲染

启动方式：
```bash
# 方式一：双击启动
web/启动知识图谱.bat

# 方式二：手动启动
python knowledge_graph_server.py
```

访问地址：http://localhost:5000

### 4. 战斗状态检测

- **战斗中检测**：通过 OCR 识别"逃跑"、"倒计时"、"技能"等关键词
- **战斗结束检测**：通过视觉特征检测大世界界面（左下角按钮、右上角地图、左上角头像）
- **历史重置**：战斗结束时自动清空对战记录和状态追踪器

## 快速开始

### 1. 安装依赖

```bash
# 运行一键安装脚本
DependencySetup_依赖库安装_win.bat

# 或手动安装核心依赖
pip install lancedb numpy flask flask-socketio
```

### 2. 配置 AI 模型

编辑 `config/ai_config.json`：

```json
{
    "current_engine": "ollama",
    "ollama_base_url": "http://127.0.0.1:11434",
    "ollama_model_id": "qwen3.5:4b",
    "ollama_no_think": true,
    "use_ai": true,
    "context_limit": 4096,
    "max_tokens": 4048,
    "temperature": 0.5
}
```

支持的引擎：`gemini`、`ollama`、`doubao`、`spark_maas`、`spark_ws`

### 3. 创建 RAG 数据库

在创建 RAG 数据库或运行对战之前，请务必先安装本地 GPU 加速的向量引擎：

```bash
# 自动检测您的显卡（NVIDIA/AMD/Intel）并安装 llama-cpp-python
python scripts/setup_llama_cpp.py
```

然后，下载您的 `.gguf` 格式的向量模型（例如 `nomic-embed-text-v1.5.Q4_K_M.gguf`）并放入 `models/` 文件夹中。

生成语义检索向量数据库：

```bash
python scripts/sync_rag_strategies.py
```

### 4. 启动知识图谱（可选）

```bash
web/启动知识图谱.bat
```

### 5. 运行主程序

1. 启动 `MFAAvalonia.exe`
2. 在 MAA 界面中选择任务并运行
3. 脚本会自动调用 `roco_pvp_ai.py` 进行战斗决策

## 配置说明

详见 [config/README.md](config/README.md)，包含：

- `ai_config.json` 所有字段说明
- 五类 AI 引擎的配置方式
- 纯规则模式的启用方法
- 数据文件格式说明
- 属性类型中英文对照表

## 属性克制表

| 属性 | 克制 | 被克制 |
|---|---|---|
| 火 | 草、虫、冰、机械 | 水、土、龙 |
| 水 | 火、土、机械 | 草、电 |
| 草 | 土、水 | 火、冰、毒、虫、龙 |
| 电 | 翼、水 | 土 |
| 冰 | 龙、翼、草、土 | 火、水、冰、机械 |
| 武 | 恶、冰、机械、普通 | 翼、超能、妖精、毒 |
| 毒 | 草、机械 | 土、超能 |
| 土 | 电、火、翼、机械、毒 | 草、水、冰 |
| 翼 | 虫、武、草 | 电、冰、土 |
| 超能 | 恶、武、毒 | 虫、幽灵、机械 |
| 虫 | 恶、草、超能 | 火、翼、幽灵 |
| 幽灵 | 幽灵、光、普通、超能 | 幽灵、恶 |
| 龙 | 龙 | 冰、龙、妖精 |
| 妖精 | 龙、恶、武 | 毒、钢 |
| 光 | 龙、恶、幽灵 | 草 |
| 恶 | 幽灵、光、超能 | 武、虫、妖精 |
| 神 | 全属性 | 无 |
| 幻 | 幽灵、超能 | 恶、武 |
| 机械 | 冰 | 火、武、土 |
| 普通 | 幽灵 | 武 |

## 更新日志

### v2.11.8 (2026-04-27)
- 新增纯规则决策模式（无需 AI 模型）
- 新增战斗结束检测与大世界 UI 识别
- 新增知识图谱 Web 可视化与实时同步
- 统一 AIClient 架构，支持五类引擎
- 新增状态记忆与技能冷却追踪
- 重构向量嵌入为 Ollama 嵌入模型
- 支持结构化 JSON 输出
- 优化 OCR 识别精度与技能匹配逻辑

## 许可证

本项目采用 MIT 许可证
