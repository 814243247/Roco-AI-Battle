# config/ 配置目录说明

本目录存放洛克王国世界 AI 助手的所有配置文件与静态数据。

---

## 文件清单

| 文件 | 说明 | 修改建议 |
|---|---|---|
| `ai_config.json` | AI 引擎核心配置 | 按需修改 API 密钥与模型参数 |
| `config.json` | MAA 框架主配置 | 一般无需手动修改 |
| `maa_option.json` | MAA 运行时选项 | 调试时可调整日志级别 |
| `instances/default.json` | 默认实例配置 | 修改脚本路径或任务列表时编辑 |
| `pet_database_full.json` | 精灵数据库 (347 只) | 数据更新时由脚本自动生成 |
| `skill_database.json` | 技能数据库 (270 个) | 数据更新时由脚本自动生成 |
| `combat_strategy_rag.jsonl` | 战斗策略知识库 | 新增策略时追加行 |

---

## ai_config.json 配置详解

```json
{
    "current_engine": "gemini",
    "use_ai": true,
    "llama_cpp_embedding_model_path": "models/nomic-embed-text-v1.5.Q4_K_M.gguf",
    "context_limit": 4096,
    "max_tokens": 4048,
    "temperature": 0.5,
    "use_text_only": true,
    "response_format": "json"
}
```

### 引擎配置（任选其一）

| 引擎 | 必填字段 | 说明 |
|---|---|---|
| `gemini` | `gemini_apikey`, `gemini_model_id` | Google Gemini API |
| `ollama` | `ollama_base_url`, `ollama_model_id` | 本地 Ollama 服务 |
| `doubao` | `doubao_api_key`, `doubao_model_id` | 字节跳动豆包 |
| `spark_maas` | `spark_maas_apikey`, `spark_maas_model_id` | 讯飞星火 MaaS |
| `spark_ws` | `spark_appid`, `spark_apikey`, `spark_apisecret` | 讯飞星火 WebSocket |

### 关键参数说明

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `current_engine` | string | `"gemini"` | 当前使用的 AI 引擎 |
| `use_ai` | bool | `true` | `true`=AI 决策, `false`=纯规则决策 |
| `llama_cpp_embedding_model_path` | string | `"models/nomic-embed-text-v1.5.Q4_K_M.gguf"` | 本地 RAG 向量模型的相对或绝对路径 |
| `context_limit` | int | `4096` | 上下文 token 上限，决定历史记录条数 |
| `max_tokens` | int | `4048` | 模型最大输出长度 |
| `temperature` | float | `0.5` | 模型温度，越低越稳定 |
| `use_text_only` | bool | `true` | `true`=纯文本模式, `false`=图文多模态 |
| `response_format` | string | `"json"` | `"json"`=结构化输出, `"text"`=自由文本 |
| `http_proxy` | string | `""` | HTTP 代理地址，国内访问 Gemini 时需要 |

### 纯规则决策模式

将 `use_ai` 设为 `false` 后，脚本将完全依赖本地规则引擎决策：

- 属性克制优先（自动选择克制敌方的技能）
- 能量智能管理（低能量时自动恢复）
- 血量危急时自动换宠（选择克制敌方的后备宠物）
- 零网络延迟、零 API 费用

---

## 数据文件说明

### pet_database_full.json

精灵完整数据库，包含 347 只精灵的以下字段：

```json
{
  "name": "火神",
  "type": "fire",
  "hp": 120,
  "attack": 110,
  "defense": 85,
  "speed": 95
}
```

### skill_database.json

技能数据库，包含 270 个技能的以下字段：

```json
{
  "name": "火焰冲击",
  "type": "fire",
  "power": 80,
  "energy_cost": 3,
  "effect": ""
}
```

### combat_strategy_rag.jsonl

战斗策略知识库，每行一条 JSON 记录：

```json
{
  "id": "水系克火系",
  "category": "属性优势",
  "scenario": "水系宠物面对火系对手",
  "action": "使用水系技能积极进攻",
  "rationale": "水系对火系造成2倍伤害",
  "source": "官方属性表"
}
```

**category 分类**：属性优势、属性劣势、换宠策略、能量管理、状态应对、宠物策略、操作技巧、战术体系

---

## 属性类型对照表

代码中使用英文属性名，UI 显示为中文：

| 英文 | 中文 | 英文 | 中文 |
|---|---|---|---|
| fire | 火 | water | 水 |
| grass | 草 | electric | 电 |
| ice | 冰 | fighting | 武 |
| poison | 毒 | ground | 土 |
| flying | 翼 | psychic | 超能 |
| bug | 虫 | ghost | 幽 |
| dragon | 龙 | dark / evil | 恶 |
| steel / mechanical | 机械 | fairy | 妖精 |
| light | 光 | normal | 普通 |
| rock | 岩 | god | 神 |
| illusion | 幻 | | |
