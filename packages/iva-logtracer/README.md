# IVA Log Tracer

IVA/Nova Session 日志追踪与分析工具。

默认安装面向 CLI 和离线分析工作流。Web backend/frontend 是可选界面，不是 trace skill 的必需依赖。

## ✨ 功能

| 功能 | 说明 | Preferred Entry |
|------|------|-----------------|
| **Init / Doctor** | 初始化配置并检查运行时环境 | `iva-logtracer init`, `iva-logtracer doctor` |
| **Session Discover** | 从业务实体稳定发现 session 列表 | `iva-logtracer discover` |
| **Session 追踪** | 跨组件日志关联追踪 | `iva-logtracer trace` |
| **Turn 分析** | 对话轮次分析与报告 | `iva-logtracer turn` |
| **Diagnostic Report** | 生成标准调查报告 | `iva-logtracer report` |
| **Audit** | KB 与 generic tool usage 审计 | `iva-logtracer audit kb|tools` |
| **Window Latency Stats** | 聚合时间窗口内 user turn latency 统计 | `python -m logtracer_extractors.scripts.window_latency_stats` |

> 💡 通用日志搜索/导出功能请使用 `kibana` 工具：`kibana-query search/export`

## 🚀 快速开始

### 1. 一键安装 CLI + Skill

如果你已经在 `share-libs` 仓库里，推荐直接运行：

```bash
bash packages/iva-logtracer/install.sh
```

这个脚本会：

- 以 editable 模式安装或刷新 `iva-logtracer` CLI，让安装版直接跟随当前 checkout
- 通过 `skills.sh` 安装 `iva-logtracer` skill（如果检测到 `npx`）
- 运行 `iva-logtracer init`
- 自动补 `~/.config/iva-logtracer/.env.lab` 和 `.env.production` 模板

如果你只想装 CLI，可以使用：

```bash
bash packages/iva-logtracer/install.sh --skip-skill
```

如果你要验证真实打包安装，而不是绑定本地源码，显式使用：

```bash
bash packages/iva-logtracer/install.sh --release-cli
```

### 2. 手动安装 CLI

开发态推荐把安装版 CLI 直接绑定到本地 clone：

```bash
uv tool install --force --editable /path/to/share-libs/packages/iva-logtracer
```

发布态或打包验证再使用真实安装：

```bash
uv tool install --force git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/iva-logtracer
```

如果你在源码仓库内开发，再使用：

```bash
uv sync
```

如果你需要 web backend，再安装 web extra:

```bash
uv sync --extra web
```

### 3. 初始化本地配置

```bash
iva-logtracer init
iva-logtracer doctor
```

默认会创建：

- `~/.config/iva-logtracer/.env`
- `~/.config/iva-logtracer/.env.example`
- `~/.cache/iva-logtracer/output/iva_session/`

编辑 `~/.config/iva-logtracer/.env` 填入你的 Elasticsearch 凭据：

```bash
KIBANA_ES_URL=https://elasticsearch.your-company.com:9200
KIBANA_USERNAME=your-username
KIBANA_PASSWORD=your-password
KIBANA_INDEX=*:*-logs-air_assistant_runtime-*
```

## 📖 使用方法

### Session Discover

从 `assistant_runtime` 日志中按业务实体发现候选 session，并输出结构化结果：

```bash
# 通过 field/value 搜索
iva-logtracer discover --env lab --last 3d --field accountId --value 17542732004

# Lucene 查询模式
iva-logtracer discover --env lab --last 24h --query 'accountId:"17542732004" AND extensionId:"17543525004"'
```

默认输出：

- `discovery_results.json`
- `discovery_results.md`

关键参数：

- `--env`
- `--last` 或 `--start/--end`
- `--field/--value` 或 `--query`
- `--index`，默认 `*:*-logs-air_assistant_runtime-*`
- `--session-key`，默认 `sessionId`
- `--page-size`，默认 `500`
- `--max-pages`，默认 `50`
- `--output-dir`
- `--format`，支持 `json`、`markdown`、`both`

输出中的 `stats` 会包含：

- `total_hits`
- `fetched_hits`
- `page_size`
- `page_count`
- `session_count`
- `complete`

Iteration 1 只覆盖 `assistant_runtime` discovery 和 session completeness；多组件 trace、summary、rule framework 仍走现有链路。

### Session 追踪

跨组件日志关联追踪 - 根据 sessionId 追踪多个组件的日志：

```bash
# 追踪 session（自动保存到 ~/.cache/iva-logtracer/output/iva_session/）
iva-logtracer trace s-abc123xyz --env production

# 指定时间范围
iva-logtracer trace s-abc123xyz --env production --last 24h

# 指定 Step 2 搜索的组件
iva-logtracer trace s-abc123xyz --env production --components agent_service nca

# 同时保存 trace JSON 文件
iva-logtracer trace s-abc123xyz --env production --save-json

# 不自动保存，只输出到终端
iva-logtracer trace s-abc123xyz --env production --no-save
```

### Turn 分析

分析追踪结果的对话轮次：

```bash
# 分析 session 目录
iva-logtracer turn ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy

# Markdown 格式输出
iva-logtracer turn ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy --format markdown

# 导出报告
iva-logtracer turn ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy -o turn_report.json
```

### Diagnostic Report / Audit

```bash
iva-logtracer report ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy
iva-logtracer report ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy \
  --reported-symptom "AIR answered wrong" --lang zh

iva-logtracer audit kb ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy
iva-logtracer audit tools ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy --format json
```

### Window Latency Stats

按线上时间窗口或已保存 session 目录聚合这 3 组关键 latency：

- `User speak end -> isFinal lag`
- `User speak end -> Filler audible`
- `Filler audio end -> Agent audible`

```bash
# 直接聚合已保存 session 目录
python -m logtracer_extractors.scripts.window_latency_stats \
  ~/.cache/iva-logtracer/output/iva_session/20260411_s-xxx-yyy \
  ~/.cache/iva-logtracer/output/iva_session/20260411_s-aaa-bbb

# 线上时间窗发现 + 复用/补抓 trace
python -m logtracer_extractors.scripts.window_latency_stats --env production \
  --account-id 37439510 \
  --start "2026-04-01T00:00:00Z" \
  --end "2026-04-01T01:00:00Z" \
  --max-sessions 10 \
  --format markdown
```

输出会包含：

- 样本数与 coverage
- `avg / p50 / p75 / p90 / p95 / max`
- `[SUSPECT]` 指标标记
- 每个指标最差的 turn 样例

注意：

- `user speak end` 与 `agent audible` 当前都是 `derived/proxy`，不是 PBX 硬真值
- 默认会在本地没有已保存 trace 时补抓会话；加 `--no-trace` 可只统计本地已有目录

**工作流程：**
1. 根据 `sessionId` 从 `assistant_runtime` 搜索日志并提取 `conversationId`
2. 使用 `conversationId` 搜索 `agent_service` 和 `nca` 的日志
3. 从 `assistant_runtime` 日志中提取 `srsSessionId`，搜索 `cprc` 的 SRS/SGS 日志

**输出目录结构：**
```
~/.cache/iva-logtracer/output/iva_session/{YYYYMMDD}_{sessionId}-{conversationId}/
├── assistant_runtime_message.log   # 组件日志 (@timestamp + message)
├── agent_service_message.log
├── nca_message.log
├── cprc_srs_message.log            # SRS (Speech Recognition) 日志
├── cprc_sgs_message.log            # SGS (Speech Generation) 日志
├── combine.log                     # 合并所有组件，按时间排序
├── summary.json                    # 汇总信息
└── *_trace.json                    # 完整 JSON (--save-json 时)
```

**支持的组件：**
| 组件 | 索引模式 | 关联字段 |
|------|---------|---------|
| `assistant_runtime` | `*:*-logs-air_assistant_runtime-*` | `sessionId`, `conversationId` |
| `agent_service` | `*:*-logs-air_agent_service-*` | `conversationId` |
| `nca` | `*:*-logs-nca-*` | `conversation_id` |
| `cprc` | `*:*-ai-cprc*` | `message` 包含 `srsSessionId` |

**组件别名：**
| 别名 | 索引模式 |
|------|---------|
| `assistant_runtime` | `*:*-logs-air_assistant_runtime-*` |
| `agent_service` | `*:*-logs-air_agent_service-*` |
| `nca` | `*:*-logs-nca-*` |
| `cprc` | `*:*-ai-cprc*` |

## ⚙️ 配置说明

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `KIBANA_ES_URL` | ✅ | Elasticsearch 服务器地址 |
| `KIBANA_USERNAME` | ⚠️ | 用户名（使用 API Key 时可省略） |
| `KIBANA_PASSWORD` | ⚠️ | 密码 |
| `KIBANA_API_KEY` | ❌ | API Key（优先于用户名密码） |
| `KIBANA_INDEX` | ❌ | 默认索引模式 |
| `KIBANA_VERIFY_CERTS` | ❌ | SSL 证书验证 (true/false) |
| `KIBANA_OUTPUT_DIR` | ❌ | 默认输出目录 |

## 🔧 高级用法

### Python API

```python
from extractors.iva import SessionTraceOrchestrator, TraceContext

# 创建追踪上下文
context = TraceContext(session_id="s-abc123xyz")

# 执行追踪
orchestrator = SessionTraceOrchestrator()
result = await orchestrator.trace(context, time_range="24h")
```
