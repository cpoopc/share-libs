# IVA Span 追踪系统设计文档

## 📋 概述

IVA Span 追踪系统是一个分布式追踪解决方案，用于分析 IVA 多组件系统中的请求链路。设计参考 **OpenTelemetry** 规范，提供完整的 Span 生命周期管理、父子关系建立和多格式导出能力。

## 🎯 设计目标

1. **完整追踪**: 从日志中提取完整的请求链路
2. **关系建立**: 自动识别 Span 之间的父子关系和因果关系
3. **性能分析**: 识别关键路径和性能瓶颈
4. **可视化**: 支持多种可视化工具 (Chrome Tracing, 自定义时间线)
5. **标准兼容**: 数据模型兼容 OpenTelemetry

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     IVA Log Sources                         │
│  (assistant_runtime, nca, aig, gmg, cprc_srs, cprc_sgs)   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Log Normalization                          │
│              (shared/log_normalizer.py)                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   Span Extractor                            │
│              (span/span_extractor.py)                       │
│  - Event matching (start/end/standalone)                    │
│  - Span creation from paired events                         │
│  - Attribute extraction                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Span Correlator                            │
│              (span/span_correlator.py)                      │
│  - Time containment analysis                                │
│  - Component call chain matching                            │
│  - Parent-child relationship establishment                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      Trace Model                            │
│                (span/span_model.py)                         │
│  - Span tree structure                                      │
│  - Critical path analysis                                   │
│  - Component statistics                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   Span Exporter                             │
│              (span/span_exporter.py)                        │
│  - JSON / Timeline JSON / Markdown                          │
│  - Chrome Tracing Format                                    │
└─────────────────────────────────────────────────────────────┘
```

## 📊 核心概念

### 1. Span

表示一个操作的时间范围，包含:

- **标识**: trace_id, span_id, parent_span_id
- **时间**: start_time, end_time, duration_ms
- **操作**: name, kind, component, operation
- **元数据**: attributes, events
- **状态**: status (OK, ERROR, CANCELLED, UNSET)

```python
@dataclass
class Span:
    trace_id: str              # 追踪 ID (conversation_id)
    span_id: str               # Span ID (唯一)
    parent_span_id: Optional[str]  # 父 Span ID
    
    start_time: datetime
    end_time: datetime
    duration_ms: float
    
    name: str                  # 显示名称
    kind: SpanKind            # INTERNAL/SERVER/CLIENT
    component: str            # 组件名称
    operation: str            # 操作类型
    
    attributes: Dict[str, Any]
    events: List[SpanEvent]
    status: SpanStatus
```

### 2. Trace

表示一次完整的追踪，包含多个 Span:

- **聚合**: 所有相关 Span 的集合
- **树形结构**: 根据父子关系组织
- **统计信息**: 组件摘要、关键路径

```python
@dataclass
class Trace:
    trace_id: str
    session_id: str
    spans: List[Span]
    
    def get_root_spans() -> List[Span]
    def get_children(parent_id) -> List[Span]
    def get_critical_path() -> List[Span]
    def get_component_summary() -> Dict
```

### 3. SpanEvent

Span 内的瞬时事件点 (无持续时间):

```python
@dataclass
class SpanEvent:
    name: str
    timestamp: datetime
    attributes: Dict[str, Any]
```

## 🔍 Span 提取流程

### 1. 事件匹配

基于 `event_registry` 定义的模式匹配日志:

```python
EVENT_REGISTRY = {
    'llm_request': {
        'start': {'patterns': [(r'request.*start', 'gmg')]},
        'end': {'patterns': [(r'Request completed', 'gmg')]},
    }
}
```

### 2. Start/End 配对

- **Start 事件**: 入栈到 `pending_starts`
- **End 事件**: 从栈中取出对应的 Start，创建 Span
- **配对键**: `{component}:{pairing_key}`

```python
key = f"{component}:{pairing_key}"
pending_starts[key].append((event_type, timestamp, data))

# 当收到 end 事件时
start_time, start_data = pending_starts[key].pop(0)
span = create_span(start_time, end_time, start_data, end_data)
```

### 3. Standalone 事件

对于单点事件 (如 error, interruption):
- 创建 duration=0 的 Span
- 或作为 SpanEvent 附加到父 Span

## 🔗 Span 关联策略

### 1. 时间包含关系

如果 Span A 的时间完全包含 Span B，则 A 可能是 B 的父:

```
Parent: |===============================|
Child:        |=============|
```

允许时间容差 (默认 100ms)

### 2. 组件调用链

根据组件间的调用顺序建立关系:

```
assistant_runtime → nca → gmg
                    ↓
                   aig → agent_service
```

### 3. 操作包含关系

某些操作逻辑上包含其他操作:

```
llm_request
  ├── generation
  │    └── first_token
  └── ...

tool_call
  └── agent_service_call
```

### 4. 评分机制

为每个候选父 Span 计算得分:

```python
score = 0
score += 100  # 基础分: 时间包含
score += 50   # 组件调用链匹配
score += 30   # 操作包含关系
score += 20   # 时间接近 (<100ms)
score += 10   # 父 Span 较小 (<1s)
```

选择得分最高的作为父 Span。

## 📤 导出格式

### 1. JSON

完整的结构化数据:

```json
{
  "trace_id": "c7b8b6fe-...",
  "spans": [
    {
      "span_id": "llm_request_nca_...",
      "parent_span_id": "answering_ar_...",
      "name": "LLM Request",
      "component": "nca",
      "start_time": "2025-12-29T18:24:58.571Z",
      "duration_ms": 305.2,
      "status": "OK",
      "attributes": {...}
    }
  ]
}
```

### 2. Timeline JSON

用于前端时间线可视化:

```json
{
  "trace_id": "c7b8b6fe-...",
  "items": [
    {
      "id": "span-1",
      "parent_id": null,
      "name": "User Turn",
      "start_ms": 0,
      "duration_ms": 2500,
      "component": "assistant_runtime"
    }
  ]
}
```

### 3. Markdown

人类可读的报告:

```markdown
# Trace Report

## Component Summary
- **nca**: 15 spans, 1250ms total
- **gmg**: 8 spans, 850ms total

## Critical Path
- [assistant_runtime] User Turn (2500ms)
  - [nca] LLM Request (1200ms)
    - [gmg] Generation (850ms)
```

### 4. Chrome Tracing Format

可在 `chrome://tracing` 中查看:

```json
[
  {
    "name": "LLM Request",
    "cat": "nca",
    "ph": "X",
    "ts": 1000,
    "dur": 305200,
    "pid": 1,
    "tid": 2
  }
]
```

## 🎯 使用场景

### 1. 性能分析

```bash
python span_trace_main.py s-abc123
```

输出关键路径，识别性能瓶颈:

```
Critical Path:
  ✅ [assistant_runtime    ] User Turn                      2500.00ms
  ✅ [nca                  ] LLM Request                    1200.00ms
  ✅ [gmg                  ] Generation                      850.00ms
  ✅ [cprc_sgs             ] TTS Synthesis                   450.00ms
```

### 2. 链路追踪

查看完整的调用链路和父子关系:

```markdown
## Span Tree
- ✅ **User Turn** [assistant_runtime] (2500ms)
  - ✅ **User Input** [assistant_runtime] (0ms)
  - ✅ **LLM Request** [nca] (1200ms)
    - ✅ **Generation** [gmg] (850ms)
      - ✅ **First Token** [gmg] (248ms)
  - ✅ **TTS Synthesis** [cprc_sgs] (450ms)
```

### 3. 错误排查

识别失败的 Span 和错误传播:

```
❌ [gmg] LLM Request (ERROR)
   Status: Timeout after 30s
   Parent: ✅ [nca] Generation Request
```

### 4. 可视化分析

导出到 Chrome Tracing 查看瀑布图:

```bash
python span_trace_main.py s-abc123 --formats chrome_tracing
# 在 chrome://tracing 中打开 trace_chrome.json
```

## 📝 关键路径算法

识别耗时最长的调用链:

```python
def get_critical_path(trace):
    # 1. 找到耗时最长的根 Span
    longest_root = max(root_spans, key=lambda s: s.duration_ms)
    
    # 2. 递归找到每一层耗时最长的子 Span
    def find_longest_child(parent):
        children = trace.get_children(parent.span_id)
        if not children:
            return [parent]
        
        longest_child = max(children, key=lambda s: s.duration_ms)
        return [parent] + find_longest_child(longest_child)
    
    return find_longest_child(longest_root)
```

## 🔄 与现有系统集成

### 与 session_tracer 集成

```python
from extractors.iva.session_tracer import SessionTraceOrchestrator
from extractors.iva.span import extract_spans_from_logs, correlate_spans

# 1. 获取日志
orchestrator = SessionTraceOrchestrator(client)
ctx = orchestrator.trace_by_session("s-abc123")
logs = ctx.get_logs()

# 2. 提取 Span
spans = extract_spans_from_logs(logs, ctx.conversation_id)

# 3. 关联 Span
trace = correlate_spans(spans)

# 4. 导出
export_trace(trace, output_dir)
```

### 与 AI Extractor 对比

| 特性 | AI Extractor | Span Tracer |
|------|-------------|-------------|
| 输出格式 | Key events list | Span tree |
| 关系建立 | 无 | 父子关系 |
| 时间信息 | Timeline offset | Duration + nesting |
| 可视化 | 文本列表 | 树形结构 + 瀑布图 |
| 用途 | AI 分析 | 性能分析 + 调试 |

两者互补:
- **AI Extractor**: 简化数据给 AI 分析
- **Span Tracer**: 完整追踪给人类调试

## 🚀 未来扩展

### 1. 实时追踪

支持流式处理，实时构建 Span:

```python
class RealtimeSpanTracer:
    def on_log(self, log):
        # 实时匹配和构建 Span
        pass
```

### 2. 采样策略

大流量场景下的采样:

```python
class SamplingStrategy:
    def should_sample(self, trace_id) -> bool:
        # 基于规则采样
        pass
```

### 3. Span Context 传播

在组件间传播 trace_id 和 span_id:

```python
# gRPC metadata
metadata = {
    'x-trace-id': trace_id,
    'x-span-id': span_id,
}
```

### 4. 聚合分析

跨多个 Trace 的统计分析:

```python
class TraceAggregator:
    def analyze(self, traces: List[Trace]):
        # P50, P95, P99 延迟
        # 错误率
        # 热点路径
        pass
```

## 📚 参考资料

- [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/)
- [Chrome Tracing Format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [Zipkin Architecture](https://zipkin.io/pages/architecture.html)

## 🤝 贡献指南

### 添加新的 Span 类型

1. 在 `event_registry.py` 中定义事件模式
2. 在 `span_extractor.py` 中添加提取逻辑
3. 在 `span_correlator.py` 中添加关联规则 (如需要)
4. 更新测试用例

### 添加新的导出格式

1. 在 `span_exporter.py` 中创建新的 Exporter 类
2. 实现 `export(trace)` 方法
3. 在 `export_trace()` 中注册

---

**设计版本**: v1.0  
**最后更新**: 2026-01-12  
**作者**: AI Assistant
