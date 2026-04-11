# Voice Call 聊天过程关键节点日志分析

本文档详细分析了 Voice Call 语音通话过程中的关键日志节点，包括时序图、状态机、逻辑分支和日志表。

## 目录

- [1. 系统架构概览](#1-系统架构概览)
- [2. 完整通话时序图](#2-完整通话时序图)
- [3. CallFsm 状态机](#3-callfsm-状态机)
- [4. 关键节点日志详解](#4-关键节点日志详解)
- [5. 逻辑分支流程图](#5-逻辑分支流程图)
- [6. 日志搜索指南](#6-日志搜索指南)

---

## 1. 系统架构概览

```mermaid
graph TB
    subgraph Client["客户端"]
        User[用户/电话]
    end

    subgraph Runtime["Runtime 服务"]
        TLS[TaskLifecycleService<br/>任务生命周期管理]
        FSM[CallFsm<br/>通话状态机]
        RC[RemoteController<br/>Agent 控制器]
        HS[HistoryService<br/>历史记录服务]
        ME[MediaEmitter<br/>媒体事件发射器]
    end

    subgraph External["外部服务"]
        SRS[SRS/SGS<br/>语音识别/合成]
        Agent[Agent Service<br/>IVA/Nova]
    end

    User <-->|音频流| SRS
    SRS <-->|gRPC| TLS
    TLS --> FSM
    FSM --> RC
    FSM --> ME
    ME --> SRS
    RC <-->|gRPC 双向流| Agent
    FSM --> HS
```

### 核心组件职责

| 组件                   | 文件路径                                    | 职责                          |
| ---------------------- | ------------------------------------------- | ----------------------------- |
| `TaskLifecycleService` | `src/tel/task/TaskLifecycleService.ts`      | 任务生命周期管理，协调各组件  |
| `CallFsm`              | `src/tel/fsm/CallFsm.ts`                    | 核心状态机，处理通话逻辑      |
| `RemoteController`     | `src/agent/controllers/RemoteController.ts` | 与 Agent Service 的 gRPC 通信 |
| `SrsHandler`           | `src/srs/SrsHandler.ts`                     | 语音识别/合成事件处理         |
| `MediaEmitter`         | `src/srs/MediaEmitter.ts`                   | 媒体事件发射器                |

---

## 2. 完整通话时序图

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户
    participant TLS as TaskLifecycleService
    participant FSM as CallFsm
    participant RC as RemoteController
    participant SRS as SRS/SGS
    participant Agent as Agent Service

    rect rgb(230, 245, 255)
    Note over TLS,Agent: 🔌 Phase 1: 连接建立
    TLS->>SRS: startSpeechRecognition()
    TLS->>SRS: startSpeechGeneration()
    TLS->>FSM: UserConnectEvent
    Note right of FSM: 📝 [state: init] Open new call conversation
    FSM->>RC: createConversation()
    RC->>Agent: agentCompletion() gRPC
    Note right of RC: 📝 Sending init request
    Agent-->>RC: AgentInitResponse
    Note right of RC: 📝 Received init
    end

    rect rgb(255, 248, 240)
    Note over FSM,Agent: 🎤 Phase 2: 问候语生成
    Note right of FSM: 📝 User connected, starting greeting
    FSM->>RC: startLlmGeneration()
    Note right of RC: 📝 Sending request
    loop 流式生成
        Agent-->>RC: generate token
        Note right of RC: 📝 Received generate
        RC-->>FSM: LlmStreamTokenEvent
        FSM->>SRS: doSay()
        Note right of FSM: 📝 Saying phrase
    end
    Agent-->>RC: end
    Note right of RC: 📝 Received end
    SRS-->>User: 播放语音
    SRS-->>FSM: VoiceGenerateEvent
    Note right of FSM: 📝 Phrase has been spoken
    end

    rect rgb(240, 255, 240)
    Note over User,FSM: 👂 Phase 3: 监听用户
    User->>SRS: 用户说话
    SRS->>FSM: TranscriptEvent
    Note right of FSM: 📝 Received transcript from user
    end

    rect rgb(255, 255, 230)
    Note over FSM,Agent: 💬 Phase 4: 生成回复
    FSM->>RC: startLlmGeneration()
    Note right of FSM: 📝 Generating response for
    loop 流式生成
        Agent-->>RC: generate
        RC-->>FSM: LlmStreamTokenEvent
        FSM->>SRS: doSay()
    end
    SRS-->>User: 播放回复
    end

    rect rgb(230, 230, 255)
    Note over User,RC: 📞 Phase 5: 通话结束
    User->>FSM: UserDisconnectEvent
    Note right of FSM: 📝 Conversation close by event
    FSM->>RC: closeConversation()
    Note right of RC: 📝 Closing conversation
    end
```

---

## 3. CallFsm 状态机

```mermaid
stateDiagram-v2
    [*] --> init: 初始化

    init --> greeting: UserConnectEvent (playGreeting=true)
    init --> listening: UserConnectEvent (重连)

    greeting --> after_greeting: VoiceEndGenerateEvent

    after_greeting --> answering: TranscriptEvent (有输入)
    after_greeting --> listening: 超时无输入

    listening --> answering: TranscriptEvent (置信度OK)
    listening --> listening: 置信度低/噪音

    answering --> cancelling: 用户打断
    answering --> listening: VoiceEndGenerateEvent (正常完成)
    answering --> after_interruption: VoiceEndGenerateEvent (被打断)
    answering --> terminating_call: 转接电话

    cancelling --> after_interruption: 取消完成

    after_interruption --> answering: 延迟后回复
    after_interruption --> listening: 无待处理文本

    terminating_call --> closed: 转接成功
    terminating_call --> answering: 转接失败

    listening --> closed: UserDisconnectEvent
    answering --> closed: UserDisconnectEvent
    greeting --> closed: UserDisconnectEvent

    closed --> [*]
```

### 状态说明

| 状态                 | 说明           | 主要日志                                   |
| -------------------- | -------------- | ------------------------------------------ |
| `init`               | 初始状态       | `Open new call conversation`               |
| `greeting`           | 播放问候语     | `Generating greeting`, `Saying phrase`     |
| `after-greeting`     | 问候后等待输入 | `Collecting phrases after greeting`        |
| `listening`          | 监听用户说话   | `Received transcript from user`            |
| `answering`          | AI 正在回答    | `Generating response for`, `Saying phrase` |
| `cancelling`         | 取消当前生成   | `Clearing speech resources`                |
| `after-interruption` | 打断后收集输入 | `Collecting phrases after interruption`    |
| `terminating-call`   | 正在转接电话   | `Terminating call started`                 |
| `closed`             | 通话结束       | `Conversation close by event`              |

---

## 4. 关键节点日志详解

### 4.1 连接建立阶段

```mermaid
flowchart TD
    A[Task 创建] --> B{Task 存在?}
    B -->|否| B1[❌ error: Task not found]
    B -->|是| C[启动 SRS/SGS]

    C --> D{SRS 连接成功?}
    D -->|否| D1[⚠️ info: Recognition error, start call transfer]
    D -->|是| E[发送 UserConnectEvent]

    E --> F[📝 info: Open new call conversation]
    F --> G{playGreeting?}
    G -->|是| G1[📝 info: User connected, starting greeting]
    G -->|否| G2[📝 info: User reconnected, starting listening]

    G1 --> H[createConversation]
    G2 --> H

    H --> I{对话已存在?}
    I -->|是| I1[📝 info: Conversation already exists]
    I -->|否| J[📝 info: Sending init request]

    J --> K{Agent 初始化}
    K -->|成功| K1[📝 info: Received init]
    K -->|失败| K2[❌ error: Received init failure]
```

| 日志级别 | 日志内容                                   | 说明                   |
| -------- | ------------------------------------------ | ---------------------- |
| `info`   | `[state: init] Open new call conversation` | 开始新通话             |
| `info`   | `User connected, starting greeting`        | 新用户，播放问候语     |
| `info`   | `User reconnected, starting listening`     | 重连用户，直接监听     |
| `info`   | `Sending init request {...}`               | 发送初始化请求到 Agent |
| `info`   | `Received init: {...}`                     | Agent 初始化成功       |
| `error`  | `Received init failure`                    | Agent 初始化失败       |
| `error`  | `Task not found`                           | Task ID 不存在         |

### 4.2 问候语生成阶段

```mermaid
flowchart TD
    A[状态: greeting] --> B[📝 info: Generating greeting]
    B --> C[📝 info: Sending request]
    C --> D[等待 Agent 响应]

    D --> E{收到 token}
    E -->|generate| F[📝 info: Received generate]
    F --> G[📝 info: Saying phrase]
    G --> H[发送 TTS 请求]
    H --> E

    E -->|end| I[📝 info: Received end]
    I --> J[📝 info: LLM generation has finished]

    J --> K{TTS 播放}
    K -->|成功| L[📝 info: Phrase has been spoken]
    K -->|失败| M[❌ error: Phrase generation has been failed]

    L --> N[📝 info: All phrases has been spoken]
    N --> O[📝 info: LLM generation and speaking has been completed]
    O --> P[状态 → after-greeting/listening]
```

### 4.3 监听阶段 (TranscriptEvent 处理)

```mermaid
flowchart TD
    A[收到 TranscriptEvent] --> B{isFinal?}

    B -->|否| C[📝 info: Received interim transcript]
    C --> D[重启静默计时器]
    D --> Z[继续监听]

    B -->|是| E[📝 info: Received transcript from user]
    E --> F{置信度检查}

    F -->|过低| G[📝 info: Confidence is too low, asking user to repeat]
    G --> H[📝 info: Asking user to repeat]
    H --> I[播放重复请求]
    I --> Z

    F -->|通过| J{短语长度检查}
    J -->|过短| K[📝 info: Ignoring the event, phrase is too short]
    K --> Z

    J -->|通过| L{噪音检测}
    L -->|是噪音| M[📝 info: Ignoring the event, noise detected]
    M --> Z

    L -->|通过| N[📝 info: Schedule fillers]
    N --> O[📝 info: Generating response for]
    O --> P[状态 → answering]
```

### 4.4 回复生成阶段

```mermaid
flowchart TD
    A[状态: answering] --> B[📝 info: Sending request]
    B --> C[等待响应]

    C --> D{响应类型}

    D -->|generate| E[📝 info: Received generate]
    E --> F[📝 info: Observed TTFT for type]
    F --> G[📝 info: Saying phrase]
    G --> C

    D -->|serverTool| H[📝 debug: Received serverTool]
    H --> C

    D -->|clientTool| I[📝 info: Calling client tool]
    I --> J{工具执行}
    J -->|成功| K[📝 info: Client tool completed]
    J -->|失败| L[❌ error: Error calling tool]
    K --> C
    L --> C

    D -->|end| M[📝 info: Received end]
    M --> N{TTS 播放}
    N -->|成功| O[📝 info: Phrase has been spoken]
    N -->|失败| P[❌ error: Phrase generation has been failed]

    O --> Q[📝 info: All phrases has been spoken]
    Q --> R[状态 → listening]
```

#### 工具调用跨组件链路（NCA → AIG → Agent Service）

在上述回复生成阶段中，如果 Agent 需要调用工具（`serverTool` / `clientTool` 分支），实际会穿过 IVA / Nova 的多个组件：

1. **Agent Service (`agent_service`)**  
   - 日志索引：`*:*-logs-air_agent_service-*`  
   - 通过 `conversationId` 与 Assistant Runtime 中的 `conversation_id` 对齐  
   - 关键日志：`serverTool`、`clientTool`、`tool completed`、`Error calling ... tool`

2. **NCA (`nca`)**  
   - 日志索引：`*:*-logs-nca-*`  
   - 同样使用 `conversation_id` 过滤  
   - 为每次工具调用生成并记录 `request_id`，包含工具调度和对话状态

3. **AIG (`aig`)**  
   - 日志索引：`*:*-logs-aig-*`  
   - 通过 `request_id` 与 NCA 日志关联（`NCA.request_id = AIG.request_id`）  
   - 记录具体的 LLM / 工具调用、延迟和错误信息

字段关联关系（与 [IVA Session Log Correlation](../../docs/log-correlation.md) 保持一致）：

| 源组件            | 目标组件      | 关联方式                              |
| ----------------- | ------------- | ------------------------------------- |
| assistant_runtime | agent_service | `conversation_id` = `conversationId`  |
| assistant_runtime | nca           | `conversation_id` = `conversation_id` |
| nca               | aig           | `request_id` = `request_id` (直接匹配) |

结合上面的时序图，排查一次工具调用问题时推荐按以下步骤关联 NCA → AIG → Agent Service 日志：

1. 在 Assistant Runtime / Voice Call 日志中，根据 `conversation_id` 和 `serverTool` / `clientTool` 关键字定位到一次工具调用。
2. 使用同一个 `conversation_id`，在 `agent_service` 和 `nca` 日志中查找对应的调用记录（会看到生成的 `request_id`）。
3. 从 NCA 日志中拿到该次调用的 `request_id`，在 `aig` 日志中搜索相同的 `request_id`，查看具体工具执行情况（包括超时、错误等），从而串联起完整链路：**NCA → AIG → Agent Service**。

### 4.5 用户打断阶段

```mermaid
flowchart TD
    A[状态: answering<br/>收到 TranscriptEvent] --> B{打断功能启用?}

    B -->|否| C[📝 info: Ignoring, interruptions disabled]
    C --> Z[继续播放]

    B -->|是| D{uninterruptible 模式?}
    D -->|是| E[📝 info: Ignoring, uninterruptible mode]
    E --> Z

    D -->|否| F{检测到停止词?}
    F -->|是| G[📝 info: Interrupting, stop words detected]
    G --> H[执行打断]

    F -->|否| I{短语长度检查}
    I -->|过短| J[📝 info: Ignoring, phrase is too short]
    J --> Z

    I -->|通过| K{噪音检测}
    K -->|是噪音| L[📝 info: Ignoring, noise detected]
    L --> Z

    K -->|通过| M[📝 info: Interrupting the generation, user is speaking]
    M --> N[📝 info: Interrupting with final transcript]
    N --> H

    H --> O[📝 info: Clearing speech resources]
    O --> P[📝 info: Cancelling LLM generation]
    P --> Q[📝 info: Sending cancel request]
    Q --> R[📝 info: Phrase has been cancelled]
    R --> S[状态 → cancelling → after-interruption]
    S --> T[延迟 1500ms 后回复]
```

### 4.6 通话结束阶段

```mermaid
flowchart TD
    A[UserDisconnectEvent] --> B[📝 info: Conversation close by event with reason]
    B --> C[状态 → closed]
    C --> D[清理资源]

    D --> E[📝 info: Closing conversation]
    E --> F{LLM 生成中?}

    F -->|是| G[等待生成完成]
    G --> H{超时?}
    H -->|是| I[⚠️ warn: Giving up on waiting for LLM]
    H -->|否| J[生成完成]
    I --> K[强制关闭]
    J --> K

    F -->|否| K

    K --> L[📝 info: Sending ConversationEndRequest]
    L --> M[📝 info: ConversationEndRequest sent]
    M --> N[📝 info: Agent service stream ended]
```

---

## 5. 逻辑分支流程图

### 5.1 完整通话流程总览

```mermaid
flowchart TB
    subgraph Init["🔌 初始化"]
        A1[创建 Task] --> A2[启动 SRS/SGS]
        A2 --> A3[UserConnectEvent]
        A3 --> A4[createConversation]
        A4 --> A5[Agent Init]
    end

    subgraph Greeting["🎤 问候语"]
        B1[generateGreeting] --> B2[LLM 生成]
        B2 --> B3[TTS 播放]
        B3 --> B4[VoiceEndGenerateEvent]
    end

    subgraph Listen["👂 监听"]
        C1[等待用户输入] --> C2{TranscriptEvent}
        C2 -->|置信度低| C3[请求重复]
        C2 -->|噪音| C4[忽略]
        C2 -->|有效输入| C5[准备回复]
        C3 --> C1
        C4 --> C1
    end

    subgraph Answer["💬 回复"]
        D1[generateResponse] --> D2[LLM 生成]
        D2 --> D3[TTS 播放]
        D3 --> D4{用户打断?}
        D4 -->|是| D5[取消生成]
        D4 -->|否| D6[播放完成]
    end

    subgraph End["📞 结束"]
        E1[UserDisconnectEvent] --> E2[关闭对话]
        E2 --> E3[清理资源]
    end

    Init --> Greeting
    Greeting --> Listen
    Listen --> Answer
    Answer -->|正常完成| Listen
    Answer -->|打断后| Listen
    Listen --> End
    Answer --> End
```

### 5.2 错误处理流程

```mermaid
flowchart TD
    subgraph Errors["错误类型"]
        E1[SRS 连接失败]
        E2[Agent 初始化失败]
        E3[LLM 生成错误]
        E4[TTS 生成失败]
        E5[gRPC 流错误]
        E6[超时错误]
    end

    subgraph Handling["错误处理"]
        H1[转接到备用号码]
        H2[重试连接]
        H3[记录错误日志]
        H4[通知用户]
    end

    E1 -->|Recognition error| H1
    E2 -->|Received init failure| H1
    E3 -->|LLM generation has failed| H1
    E4 -->|Phrase generation failed| H3
    E5 -->|可恢复| H2
    E5 -->|致命| H1
    E6 -->|Voice generation timeout| H3

    subgraph Logs["关键错误日志"]
        L1["❌ error: Task not found"]
        L2["❌ error: Agent service error"]
        L3["❌ error: LLM generation has failed"]
        L4["❌ error: Phrase generation has been failed"]
        L5["❌ error: Agent service stream ended with fatal error"]
        L6["⚠️ warn: Giving up on waiting for LLM"]
    end
```

---

## 6. 日志搜索指南

### 6.1 按阶段搜索日志

```bash
# 查看完整通话流程
grep -E "Open new call|starting greeting|Generating greeting|Received transcript|Generating response|Conversation close" logs.txt

# 查看连接建立
grep -E "Open new call|Sending init|Received init" logs.txt

# 查看语音生成
grep -E "Saying phrase|Phrase has been spoken|All phrases" logs.txt

# 查看用户输入
grep -E "Received.*transcript|TranscriptEvent" logs.txt
```

### 6.2 按问题类型搜索

```bash
# 查看所有错误
grep -E "error|failed|timeout|fatal" logs.txt

# 查看用户打断
grep -E "Interrupting|cancelled|cancel" logs.txt

# 查看低置信度/噪音过滤
grep -E "Confidence is too low|noise detected|phrase is too short" logs.txt

# 查看状态变化
grep -E "\[state:" logs.txt

# 查看工具调用
grep -E "clientTool|serverTool|Calling client tool|tool completed" logs.txt
```

### 6.3 按 conversationId 过滤

```bash
# 替换 YOUR_CONVERSATION_ID 为实际 ID
grep "YOUR_CONVERSATION_ID" logs.txt
```

### 6.4 关键指标日志

```bash
# 查看 TTFT (Time To First Token)
grep "Observed TTFT" logs.txt

# 查看超时
grep -E "timeout|DEADLINE_EXCEEDED" logs.txt

# 查看重连
grep "Restarting agent service stream" logs.txt
```

---

## 7. 完整日志表

### 7.1 正常流程日志

| 阶段 | 状态      | 日志级别 | 日志内容                                            | 来源             |
| ---- | --------- | -------- | --------------------------------------------------- | ---------------- |
| 连接 | init      | `info`   | `Open new call conversation`                        | CallFsm          |
| 连接 | init      | `info`   | `User connected, starting greeting`                 | CallFsm          |
| 连接 | -         | `info`   | `Sending init request {...}`                        | RemoteController |
| 连接 | -         | `info`   | `Received init: {...}`                              | RemoteController |
| 问候 | greeting  | `info`   | `Generating greeting ...`                           | CallFsm          |
| 问候 | greeting  | `info`   | `Saying phrase: ...`                                | CallFsm          |
| 问候 | greeting  | `info`   | `Received generate: {...}`                          | RemoteController |
| 问候 | greeting  | `info`   | `LLM generation has finished`                       | CallFsm          |
| 问候 | greeting  | `info`   | `Phrase has been spoken: ...`                       | CallFsm          |
| 问候 | greeting  | `info`   | `All phrases has been spoken`                       | CallFsm          |
| 监听 | listening | `info`   | `Received interim transcript from user`             | CallFsm          |
| 监听 | listening | `info`   | `Received transcript from user`                     | CallFsm          |
| 回复 | answering | `info`   | `Schedule fillers in state: listening`              | CallFsm          |
| 回复 | answering | `info`   | `Generating response for: ...`                      | CallFsm          |
| 回复 | answering | `info`   | `Sending request {...}`                             | RemoteController |
| 回复 | answering | `info`   | `Observed TTFT for type: ...ms`                     | RemoteController |
| 回复 | answering | `info`   | `Saying phrase: ...`                                | CallFsm          |
| 回复 | answering | `info`   | `Phrase has been spoken: ...`                       | CallFsm          |
| 结束 | closed    | `info`   | `Conversation close by event: ... with reason: ...` | CallFsm          |
| 结束 | -         | `info`   | `Closing conversation ...`                          | RemoteController |
| 结束 | -         | `info`   | `Agent service stream ended`                        | RemoteController |

### 7.2 打断流程日志

| 阶段 | 状态               | 日志级别 | 日志内容                                          | 来源             |
| ---- | ------------------ | -------- | ------------------------------------------------- | ---------------- |
| 打断 | answering          | `info`   | `Interrupting the generation, user is speaking`   | CallFsm          |
| 打断 | answering          | `info`   | `Interrupting with final transcript: ...`         | CallFsm          |
| 打断 | cancelling         | `info`   | `Clearing speech resources`                       | CallFsm          |
| 打断 | -                  | `info`   | `Cancelling LLM generation for conversation: ...` | RemoteController |
| 打断 | -                  | `info`   | `Sending cancel request {...}`                    | RemoteController |
| 打断 | cancelling         | `info`   | `Phrase has been cancelled: ...`                  | CallFsm          |
| 打断 | after-interruption | `info`   | `Collecting phrases after interruption ...`       | CallFsm          |

### 7.3 异常/过滤日志

| 场景     | 日志级别 | 日志内容                                           | 来源    |
| -------- | -------- | -------------------------------------------------- | ------- |
| 置信度低 | `info`   | `Confidence is too low, asking user to repeat`     | CallFsm |
| 噪音     | `info`   | `Ignoring the event, noise detected`               | CallFsm |
| 短语过短 | `info`   | `Ignoring the event, phrase is too short`          | CallFsm |
| 停止词   | `info`   | `Interrupting the generation, stop words detected` | CallFsm |
| 打断禁用 | `info`   | `Ignoring the event, interruptions are disabled`   | CallFsm |
| 不可打断 | `info`   | `Ignoring the event, uninterruptible mode`         | CallFsm |

### 7.4 错误日志

| 场景         | 日志级别 | 日志内容                                                | 来源                 |
| ------------ | -------- | ------------------------------------------------------- | -------------------- |
| Task 不存在  | `error`  | `Task not found`                                        | TaskLifecycleService |
| Agent 错误   | `error`  | `Agent service error: ...`                              | RemoteController     |
| 初始化失败   | `error`  | `Received init failure`                                 | RemoteController     |
| LLM 失败     | `error`  | `LLM generation has failed: ...`                        | CallFsm              |
| TTS 失败     | `error`  | `Phrase generation has been failed: ...`                | CallFsm              |
| 工具调用失败 | `error`  | `Error calling ... tool: ...`                           | RemoteController     |
| gRPC 流关闭  | `error`  | `Cannot send generation request, GRPC stream is closed` | SrsHandler           |
| 致命错误     | `error`  | `Agent service stream ended with fatal error`           | RemoteController     |
| 等待超时     | `warn`   | `Giving up on waiting for LLM generation to finish`     | RemoteController     |
| 语音超时     | `info`   | `Voice generation timeout`                              | CallFsm              |

---

## 8. 时间线示例

一个典型的成功通话日志时间线：

```
[00:00.000] [state: init] Open new call conversation
[00:00.010] [state: init] User connected, starting greeting
[00:00.015] Sending init request {...}
[00:00.050] Received init: {...}
[00:00.055] [state: greeting] Generating greeting ...
[00:00.060] Sending request {...}
[00:00.150] Received generate: {...}
[00:00.155] [state: greeting] Saying phrase: "您好，..."
[00:00.300] Received generate: {...}
[00:00.305] [state: greeting] Saying phrase: "请问有什么..."
[00:00.400] Received end: {...}
[00:00.405] [state: greeting] LLM generation has finished
[00:01.500] [state: greeting] Phrase has been spoken: "您好，..."
[00:02.800] [state: greeting] Phrase has been spoken: "请问有什么..."
[00:02.805] [state: greeting] All phrases has been spoken
[00:02.810] LLM generation and speaking has been completed
[00:05.000] [state: listening] Received interim transcript from user
[00:06.500] [state: listening] Received transcript from user
[00:06.510] [state: listening] Schedule fillers in state: listening
[00:06.515] [state: answering] Generating response for: "我想查询..."
[00:06.520] Sending request {...}
[00:06.700] Received generate: {...}
[00:06.702] Observed TTFT for type text: 180ms
[00:06.705] [state: answering] Saying phrase: "好的，..."
[00:07.500] Received end: {...}
[00:08.200] [state: answering] Phrase has been spoken: "好的，..."
[00:08.205] [state: answering] All phrases has been spoken
[00:15.000] Conversation close by event: UserDisconnectEvent with reason: user_hangup
[00:15.005] Closing conversation ...
[00:15.010] Sending ConversationEndRequest for conversation ...
[00:15.015] ConversationEndRequest sent for conversation ...
[00:15.050] Agent service stream ended
```
