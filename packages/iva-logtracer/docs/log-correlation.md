# IVA Session Log Correlation

本文档介绍 IVA Session Trace 中各组件日志的关联查询路径。

## 概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           IVA Session Trace                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Round 1                                                                     │
│  ┌──────────────────────┐                                                   │
│  │  assistant_runtime   │ ◄── session_id                                    │
│  └──────────┬───────────┘                                                   │
│             │                                                                │
│             ▼ 提取: conversation_id, srs_session_id, sgs_session_id         │
│                                                                              │
│  Round 2 (并发)                                                              │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────┐  ┌──────────┐           │
│  │ agent_service│  │   cprc_srs    │  │ cprc_sgs │  │   nca    │           │
│  └──────────────┘  └───────────────┘  └──────────┘  └────┬─────┘           │
│         ▲                  ▲                ▲             │                  │
│         │                  │                │             │                  │
│   conversation_id    srs_session_id   sgs_session_id     │                  │
│                                                           │                  │
│                                                           ▼ 提取: request_id │
│  Round 3 (并发)                                                              │
│  ┌──────────┐  ┌──────────┐                                                 │
│  │   aig    │  │   gmg    │                                                 │
│  └──────────┘  └──────────┘                                                 │
│        ▲             ▲                                                       │
│        │             │                                                       │
│   request_id    log_context_RCRequestId                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 组件关联详情

### Round 1: AssistantRuntime

| 组件 | Index Pattern | 输入字段 | 查询字段 |
|------|---------------|----------|----------|
| assistant_runtime | `*:*-logs-air_assistant_runtime-*` | `session_id` | `sessionId` |

**派生数据提取：**
- `conversation_id`: 从日志的 `conversationId` 字段提取
- `srs_session_id`: 从日志消息中匹配 `SRS SessionId: {uuid}` 模式
- `sgs_session_id`: 从日志消息中匹配 `SGS SessionId: {uuid}` 模式

---

### Round 2: 并发加载 (依赖 Round 1)

| 组件 | Index Pattern | 依赖字段 | 查询字段 |
|------|---------------|----------|----------|
| agent_service | `*:*-logs-air_agent_service-*` | `conversation_id` | `conversationId` |
| nca | `*:*-logs-nca-*` | `conversation_id` | `conversation_id` |
| cprc_srs | `*:*-logs-cprc-*` | `srs_session_id` | `sessionId` + `message:SRS` |
| cprc_sgs | `*:*-logs-cprc-*` | `sgs_session_id` | `sessionId` + `message:SGS` |

---

### Round 3: 并发加载 (依赖 NCA 日志)

| 组件 | Index Pattern | 依赖 | 源字段 | 目标字段 |
|------|---------------|------|--------|----------|
| aig | `*:*-logs-aig-*` | `logs.nca` | NCA.`request_id` | AIG.`request_id` |
| gmg | `*:*-logs-gmg-*` | `logs.nca` | NCA.`request_id` | GMG.`log_context_RCRequestId` |

---

## 调用链路

```
用户请求
    │
    ▼
┌─────────────────────┐
│  Assistant Runtime  │  ◄── 入口，记录 session_id
└─────────┬───────────┘
          │
          ▼
    ┌─────────────┐
    │   NCA       │  ◄── 对话协调器
    └──────┬──────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐  ┌─────────┐
│   AIG   │  │   GMG   │  ◄── AI 网关组件
└─────────┘  └─────────┘
```

## 关联字段映射

| 源组件 | 目标组件 | 关联方式 |
|--------|----------|----------|
| assistant_runtime | agent_service | `conversation_id` = `conversationId` |
| assistant_runtime | nca | `conversation_id` = `conversation_id` |
| assistant_runtime | cprc_srs | `srs_session_id` = `sessionId` |
| assistant_runtime | cprc_sgs | `sgs_session_id` = `sessionId` |
| nca | aig | `request_id` = `request_id` (直接匹配) |
| nca | gmg | `request_id` = `log_context_RCRequestId` |

## 使用示例

```bash
# 按 session_id 追踪
iva-logtracer trace s-xxx --env production --save-json

# 按 conversation_id 追踪
iva-logtracer trace c7b8b6fe-a5fa-4151-89d6-51782bf08e23 --env production --save-json
```

## 输出文件

追踪完成后，默认会在 `~/.cache/iva-logtracer/output/iva_session/{trace_dir}/` 目录下生成：

- `assistant_runtime_trace.json` - Assistant Runtime 日志
- `agent_service_trace.json` - Agent Service 日志
- `nca_trace.json` - NCA 日志
- `aig_trace.json` - AIG 日志
- `gmg_trace.json` - GMG 日志
- `cprc_srs_trace.json` - CPRC SRS 日志
- `cprc_sgs_trace.json` - CPRC SGS 日志
- `combine.log` - 合并后的时间线日志
