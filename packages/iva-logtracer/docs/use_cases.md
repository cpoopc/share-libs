# IVA Log Tracer 使用场景分析

## 1. 产品定位
IVA Log Tracer 是一个专为 **IVA (Intelligent Virtual Assistant)** 开发者和运维人员设计的**跨组件日志追踪与诊断工具**。它旨在解决分布式微服务架构下，难以通过单一会话 ID (`sessionId`) 完整复原用户交互全链路的问题。

## 2. 核心痛点与解决方案

| 痛点 | IVA Log Tracer 解决方案 |
|------|------------------------|
| **碎片化日志** <br> 日志分散在 Assistant Runtime, Agent Service, NCA, CPRC 等多个组件，难以手动关联。 | **Session 级全链路追踪** <br> 通过 `sessionId` 自动串联所有相关组件的日志。系统会自动提取 `conversationId` 和 `srsSessionId` 等二级关联 ID，实现一键式跨组件检索。 |
| **时序错乱** <br> 不同组件的日志时间戳可能存在偏差，难以还原真实的交互时序。 | **统一时间轴视图** <br> 提供多面板对照视图 (Multi-component View)，支持**时间轴同步 (Time Sync)**，并在导出时提供合并的时间序日志 (`combine.log`)。 |
| **排查效率低** <br> 在海量日志中检索特定错误或关键字非常耗时。 | **高效过滤与搜索** <br> 支持正则表达式 (Regex)、多关键字搜索、日志级别过滤 (ERROR/WARN)，并能保存常用过滤器。 |
| **交互逻辑晦涩** <br> 难以直观理解对话轮次 (Turn) 的流转状态。 | **Turn 分析 (Turn Analysis)** <br> 自动解析对话轮次，生成结构化的 Turn 报告，清晰展示每个 Turn 的组件交互流程 (如 `tool call`, `llm request` 等)。 |

## 3. 主要使用场景 (Use Cases)

### 场景一：线上问题复现与诊断 (On-call Troubleshooting)
**用户角色**：SRE / 开发人员
**目标**：快速定位用户反馈的 "IVA 不回复" 或 "回复错误" 问题。
**流程**：
1.  获取用户提供的 `sessionId`。
2.  运行 `iva-logtracer trace <sessionId> --env production --save-json`。
3.  系统自动拉取 AR, NSA, Agent Service 等组件的日志。
4.  开启 **Time Sync** 功能，滚动查看各组件在同一时刻的行为。
5.  使用 **Log Level: ERROR** 快速定位报错节点 (例如：Agent Service 超时，或 NCA 模型生成失败)。

### 场景二：对话交互调优 (Dialogue Flow Optimization)
**用户角色**：算法工程师 / 对话设计师
**目标**：分析特定场景下的多轮对话逻辑是否符合预期。
**流程**：
1.  使用 `iva-logtracer turn <saved-trace-dir>` 分析历史会话。
2.  查看生成的 Markdown 报告，检查每个 Turn 的关键节点：
    *   ASR 识别结果 (`cprc_srs`)
    *   NCA 的 Tool Call 参数是否准确
    *   Agent Service 的调用耗时
3.  对比预期逻辑与实际日志路径，优化 Prompt 或业务逻辑。

### 场景三：性能瓶颈分析 (Latency Debugging)
**用户角色**：性能优化工程师
**目标**：分析端到端延迟 (End-to-End Latency) 高的原因。
**流程**：
1.  在前端页面加载多个关键组件 (AR, Agent Service, NCA) 的面板。
2.  观察同一请求在组件间的流转时间戳。
3.  通过日志时间差识别耗时最长的环节 (例如：是网络传输慢，还是 LLM Token 生成慢)。

### 场景四：本地开发调试 (Local Development)
**用户角色**：后端开发人员
**目标**：调试新开发的 Agent 或 Tool。
**流程**：
1.  本地运行微服务，日志接入测试环境 ES。
2.  利用 Log Tracer 的 **Live Mode** (实时刷新)，一边与 Bot 交互，一边实时观测各服务日志输出。
3.  使用 Regex 过滤器只关注特定函数或模块的日志。

## 4. 技术架构亮点
-   **Backend**: Python FastAPI, 集成 Elasticsearch/Kibana Client，负责复杂的日志查询与关联逻辑。
-   **Frontend**: React + Vite + Tailwind，提供类似 IDE 的多窗口并排体验，支持虚拟滚动 (Virtual Scroll) 以流畅展示海量日志。
-   **CLI**: 提供 `iva-logtracer trace|turn|report|audit` 等命令，方便脚本化调用和生成离线报告。
