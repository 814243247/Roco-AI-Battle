# 洛克王国世界 AI 助手 (MFAAvalonia)

洛克王国世界游戏的 AI 自动化助手，基于 MFAAvalonia 框架，支持智能战斗、任务自动化、RAG 知识库等功能。

## 📋 项目概述

本项目是一个完整的洛克王国世界游戏 AI 助手，提供以下核心功能：

- **自动化战斗**: 基于图像识别和 AI 决策的自动战斗系统
- **RAG 知识库**: 基于 LanceDB 的精灵和技能知识库，支持中文语义检索
- **PVP 专家系统**: 自动分析战局并制定策略
- **多模型支持**: 集成豆包、Gemini 等多个 AI 模型
- **跨平台支持**: 基于 Avalonia UI，支持 Windows 平台

## 🏗️ 项目结构

```
MFAAvalonia-v2.11.8-win-x64/
├── 📁 ai_life/                        # AI 日志
│   ├── README.md                     # AI 生命系统说明
│   └── dev_log_2026-04-15.md         # 开发日志（多 AI 协作同步）
├── 📁 config/                         # 配置文件目录
│   ├── instances/default.json        # 实例配置
│   ├── ai_config.json                # AI 配置
│   ├── config.json                   # 主配置
│   ├── maa_option.json               # MAA 选项
│   ├── pet_database_full.json        # 完整精灵数据库 (347 只)
│   └── skill_database.json           # 技能数据库 (270 个)
├── 📁 libs/                           # 依赖库
│   ├── MaaAgentBinary/               # MAA 代理二进制
│   │   ├── maatouch/                 # 触摸模拟
│   │   ├── minicap/                  # 屏幕捕获
│   │   └── minitouch/                # 触摸控制
│   ├── locales/                      # 多语言资源
│   └── *.dll                         # 核心库文件
├── 📁 plugins/                        # 插件目录
│   └── win-x64/MaaPluginDemo.dll
├── 📁 prompts/                        # AI 提示词模板
│   └── pvp_prompt.txt
├── 📁 pvp_resource/                   # PVP 资源
│   └── pipeline/task.json
├── 📁 resource/                       # 游戏资源
│   ├── base/pipeline/sample.json
│   └── mfa_layout.json
├── 📁 runtimes/                       # 运行时库
│   └── win-x64/native/               # 原生库
├── 📁 scripts/                        # Python 脚本工具
│   ├── 📁 rag_db/                    # ChromaDB 数据库 (旧版)
│   ├── 📁 rag_lancedb/               # LanceDB 数据库 (当前)
│   │   ├── pets.lance/               # 精灵数据表 (347 条)
│   │   └── skills.lance/             # 技能数据表 (270 条)
│   ├── generate_full_pet_db.py       # 生成精灵数据库
│   ├── create_rag_db_lancedb.py      # 创建 LanceDB 数据库
│   ├── test_rag_db_lancedb.py        # 测试 LanceDB 数据库
│   ├── update_pet_weaknesses.py      # 更新精灵克制关系
│   └── check_db.py                   # 数据库检查工具
├── 📁 test_evidence/                  # 测试证据
│   └── *.jpg
├── 📁 tests/                          # 测试脚本
│   ├── test_gemini_3_expert.py
│   └── test_pvp_expert.py
├── 📄 README.md                       # 项目说明
├── 📄 MFAAvalonia.exe                # 主程序
├── 📄 appsettings.json               # 应用设置
├── 📄 interface.json                 # 接口配置
├── 📄 roco_pvp_ai.py                 # PVP AI 主脚本
└── 📄 DependencySetup_依赖库安装_win.bat  # 依赖安装脚本
```

## 🗂️ 文件拓扑图

```
┌─────────────────────────────────────────────────────────────────┐
│                    MFAAvalonia 主程序层                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │MFAAvalonia  │  │appsettings.  │  │interface.json        │   │
│  │.exe         │  │json          │  │(接口配置)            │   │
│  │(主程序)     │  │(应用设置)    │  └──────────────────────┘   │
│  └─────────────┘  └──────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      核心功能层                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ai_life/         │  │pvp_resource/    │  │prompts/         │  │
│  │(AI 日志)     │  │(PVP 资源)       │  │(AI 提示词)       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      数据层                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │config/          │  │scripts/         │  │resource/        │  │
│  │(配置文件)       │  │(Python 脚本)     │  │(游戏资源)       │  │
│  ├─pet_database    │  ├─rag_lancedb/    │  └─────────────────┘  │
│  ├─skill_database  │  │  ├─pets.lance   │                       │
│  └─ai_config       │  │  └─skills.lance │                       │
│  └─────────────────┘  └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      运行时层                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │libs/            │  │runtimes/        │  │plugins/         │  │
│  │(依赖库)         │  │(运行时库)       │  │(插件)           │  │
│  ├─MaaAgentBinary  │  │└─win-x64/native/│  │└─win-x64/       │  │
│  ├─*.dll           │  │  └─*.dll        │  │  └─*.dll        │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 🔧 核心文件说明

### 主程序文件
- **MFAAvalonia.exe**: Windows 主程序，基于 Avalonia UI 框架
- **appsettings.json**: 应用程序配置文件
- **interface.json**: 接口定义和配置
- **roco_pvp_ai.py**: PVP AI 主脚本（自动化战斗）

### ai_life 模块 ⭐
- **开发日志**: 多 AI 协作同步日志。生成日志，插入到当天日期的日志，没有没有生成新日期日志。

### 核心情报与对战指南 (Battle Intelligence) ⭐
- **[docs/BATTLE_INTELLIGENCE.md](file:///D:/Project/AutoPlayGame/MFAAvalonia-v2.11.8-win-x64/docs/BATTLE_INTELLIGENCE.md)**: 汇总 B 站、抖音及开源项目的核心对战思路，作为 RAG 知识库的顶级战术指南。

### 配置文件
- **config/config.json**: 主配置文件
- **config/ai_config.json**: AI 模型配置（豆包、Gemini 等）
- **config/instances/default.json**: 默认实例配置
- **config/maa_option.json**: MAA 框架选项

### 数据库文件
- **config/pet_database_full.json**: 347 只精灵的完整数据库
- **config/skill_database.json**: 270 个技能的数据库
- **scripts/rag_lancedb/pets.lance**: LanceDB 精灵向量数据库
- **scripts/rag_lancedb/skills.lance**: LanceDB 技能向量数据库

### Python 脚本
- **generate_full_pet_db.py**: 生成完整精灵数据库
- **create_rag_db_lancedb.py**: 创建 LanceDB 向量数据库
- **test_rag_db_lancedb.py**: 测试 LanceDB 数据库功能
- **update_pet_weaknesses.py**: 更新精灵属性克制关系
- **roco_pvp_ai.py**: PVP AI 主脚本

### 测试文件
- **tests/test_gemini_3_expert.py**: Gemini 3 模型测试
- **tests/test_pvp_expert.py**: PVP 专家系统测试
- **test_doubao_connection.py**: 豆包模型连接测试

## 🚀 快速开始

### 1. 安装依赖

```bash
# 运行依赖安装脚本
DependencySetup_依赖库安装_win.bat

# 手动安装 Python 依赖
pip install lancedb numpy
```

### 2. 配置 AI 模型

编辑 `config/ai_config.json`，配置你的 AI 模型 API 密钥：

```json
{
  "doubao": {
    "api_key": "your_api_key",
    "model": "doubao-pro-4k"
  },
  "gemini": {
    "api_key": "your_api_key",
    "model": "gemini-3"
  }
}
```

### 3. 创建 RAG 数据库

```bash
cd scripts
python create_rag_db_lancedb.py
```

### 4. 测试数据库

```bash
python test_rag_db_lancedb.py
```

### 5. 运行主程序

```bash
MFAAvalonia.exe
```

## 📊 数据库统计

### 精灵数据库
- **总数**: 347 只精灵
- **属性类型**: 20+ 种（fire, water, grass, electric, light, fairy 等）
- **数据来源**: 官方数据整理

### 技能数据库
- **总数**: 270 个技能
- **技能类型**: 物攻、魔攻、状态
- **属性覆盖**: 全属性技能

### LanceDB 向量数据库
- **向量维度**: 384
- **精灵表**: 347 条记录
- **技能表**: 270 条记录
- **平均查询时间**: < 0.01s

## 🔍 属性克制表

数据库使用英文属性名，包含以下属性：
- `fire` (火), `water` (水), `grass` (草)
- `electric` (电), `ice` (冰), `ground` (土)
- `flying` (翼), `poison` (毒), `fighting` (武)
- `psychic` (超能), `evil` (恶), `ghost` (幽)
- `dragon` (龙), `mechanical` (机械), `light` (光)
- `fairy` (妖精)
- `bug` (虫), `rock` (岩), `normal` (普通)

## 📝 更新日志

### v2.11.8 (2026-04-15)
- ✅ 迁移 RAG 数据库从 ChromaDB 到 LanceDB
- ✅ 支持中文语义检索
- ✅ 修正精灵属性数据（白金独角兽：divine_fairy → light）
- ✅ 添加完整的克制关系计算
- ✅ 改进 PVP AI 决策系统
- ✅ 完善项目文档和开发日志

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证

## 📞 联系方式

- 项目地址：https://github.com/your-repo/MFAAvalonia
- 问题反馈：请提交 Issue

---

**注意**: 本项目仅供学习和研究使用，请勿用于商业目的。
