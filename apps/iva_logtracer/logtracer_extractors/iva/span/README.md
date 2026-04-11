# IVA Span 追踪系统

> 🔍 分布式追踪系统，用于分析 IVA 多组件系统中的请求链路

## 📦 功能特性

- ✅ **自动 Span 提取**: 从日志中自动识别和配对 start/end 事件
- ✅ **智能关联**: 基于时间、组件和操作的父子关系建立
- ✅ **性能分析**: 识别关键路径和性能瓶颈
- ✅ **多格式导出**: JSON, Timeline, Markdown, Chrome Tracing
- ✅ **可视化支持**: 兼容 Chrome DevTools, Jaeger 等工具
- ✅ **OpenTelemetry 兼容**: 数据模型符合 OTel 规范

## 🚀 快速开始

### 基本用法

```bash
# 从 Kibana 查询并分析
python span_trace_main.py s-abc123

# 从本地文件分析
python span_trace_main.py --input logs.json --conversation-id c7b8b6fe-...
```

### Python API

```python
from extractors.iva.span import extract_spans_from_logs, correlate_spans, export_trace

# 1. 提取 Span
spans = extract_spans_from_logs(logs, conversation_id="c7b8b6fe-...")

# 2. 关联 Span (建立父子关系)
trace = correlate_spans(spans)

# 3. 分析
print(f"Total spans: {len(trace.spans)}")
print(f"Root spans: {len(trace.get_root_spans())}")
print(f"Components: {list(trace.get_component_summary().keys())}")

# 4. 获取关键路径
critical_path = trace.get_critical_path()
for span in critical_path:
    print(f"  [{span.component}] {span.name} - {span.duration_ms:.2f}ms")

# 5. 导出
export_trace(trace, output_dir, formats=["json", "markdown", "chrome_tracing"])
```

## 📊 输出格式

### 1. trace.json

完整的结构化数据:

```json
{
  "trace_id": "c7b8b6fe-a5fa-4151-89d6-51782bf08e23",
  "session_id": "s-a7860201cfd2dz19b6b5ad7daz59c66c80000",
  "spans": [
    {
      "span_id": "llm_request_nca_1767032698.571",
      "parent_span_id": "answering_assistant_runtime_1767032698.566",
      "name": "LLM Request",
      "component": "nca",
      "operation": "llm_request",
      "start_time": "2025-12-29T18:24:58.571Z",
      "end_time": "2025-12-29T18:24:58.876Z",
      "duration_ms": 305.2,
      "status": "OK",
      "attributes": {
        "llm_type": "chitchat",
        "model": "gpt-4.1"
      }
    }
  ],
  "component_summary": {
    "nca": {
      "span_count": 15,
      "total_duration_ms": 1250.5,
      "avg_duration_ms": 83.37,
      "error_count": 0
    }
  }
}
```

### 2. timeline.json

用于前端时间线可视化:

```json
{
  "trace_id": "c7b8b6fe-...",
  "start_time": "2025-12-29T18:24:36.124Z",
  "duration_ms": 25432.5,
  "items": [
    {
      "id": "span-1",
      "parent_id": null,
      "name": "User Turn",
      "component": "assistant_runtime",
      "start_ms": 0,
      "duration_ms": 2500,
      "status": "OK"
    }
  ]
}
```

### 3. trace.md

Markdown 报告:

```markdown
# Trace Report: c7b8b6fe-...

**Duration**: 25432.50 ms
**Total Spans**: 47

## Component Summary

### nca
- Span Count: 15
- Total Duration: 1250.50 ms
- Avg Duration: 83.37 ms

## Critical Path

The longest execution path:
- [assistant_runtime] User Turn (2500.00ms)
  - [nca] LLM Request (1200.00ms)
    - [gmg] Generation (850.00ms)

## Span Tree

- ✅ **Session Create** [assistant_runtime] (50.00ms)
- ✅ **User Turn** [assistant_runtime] (2500.00ms)
  - ✅ **User Input** [assistant_runtime] (0.00ms)
  - ✅ **LLM Request** [nca] (1200.00ms)
    - ✅ **Generation** [gmg] (850.00ms)
```

### 4. trace_chrome.json

Chrome Tracing Format - 在 `chrome://tracing` 中打开:

```json
[
  {
    "name": "LLM Request",
    "cat": "nca",
    "ph": "X",
    "ts": 20000,
    "dur": 305200,
    "pid": 1,
    "tid": 2,
    "args": {
      "span_id": "llm_request_nca_...",
      "status": "OK",
      "model": "gpt-4.1"
    }
  }
]
```

## 🔍 关键概念

### Span

表示一个操作的时间范围:

```python
Span(
    trace_id="c7b8b6fe-...",        # 追踪 ID
    span_id="llm_request_nca_...",  # Span ID
    parent_span_id="answering_...", # 父 Span ID
    
    name="LLM Request",             # 显示名称
    component="nca",                # 组件
    operation="llm_request",        # 操作类型
    
    start_time=datetime(...),       # 开始时间
    end_time=datetime(...),         # 结束时间
    duration_ms=305.2,              # 持续时间
    
    attributes={...},               # 属性
    status=SpanStatus.OK,           # 状态
)
```

### Trace

一次完整的追踪:

```python
trace = Trace(
    trace_id="c7b8b6fe-...",
    session_id="s-a7860201cfd2d...",
    spans=[...]
)

# 查询
root_spans = trace.get_root_spans()
children = trace.get_children(parent_span_id)
tree = trace.get_span_tree()

# 分析
critical_path = trace.get_critical_path()
summary = trace.get_component_summary()
```

## 📈 分析示例

### 性能瓶颈识别

```python
# 找出耗时最长的 Span
slow_spans = sorted(trace.spans, key=lambda s: s.duration_ms or 0, reverse=True)[:10]

for span in slow_spans:
    print(f"{span.name}: {span.duration_ms:.2f}ms ({span.component})")
```

### 组件统计

```python
summary = trace.get_component_summary()

for component, stats in summary.items():
    print(f"{component}:")
    print(f"  Spans: {stats['span_count']}")
    print(f"  Total: {stats['total_duration_ms']:.2f}ms")
    print(f"  Avg: {stats['avg_duration_ms']:.2f}ms")
    print(f"  Errors: {stats['error_count']}")
```

### 错误追踪

```python
# 找出所有错误 Span
error_spans = [s for s in trace.spans if s.status == SpanStatus.ERROR]

for span in error_spans:
    print(f"❌ [{span.component}] {span.name}")
    print(f"   {span.status_message}")
    
    # 找出父 Span (错误传播链)
    parent = trace.get_span_by_id(span.parent_span_id)
    if parent:
        print(f"   Parent: [{parent.component}] {parent.name}")
```

## 🎯 关联策略

Span 之间的父子关系基于以下规则建立:

1. **时间包含**: 父 Span 的时间范围包含子 Span
2. **组件调用链**: assistant_runtime → nca → gmg
3. **操作包含**: llm_request 包含 generation
4. **评分机制**: 综合多个因素计算最佳父 Span

详细算法见 [DESIGN.md](./DESIGN.md)

## 📂 项目结构

```
span/
├── __init__.py           # 模块导出
├── span_model.py         # 数据模型 (Span, Trace)
├── span_extractor.py     # Span 提取器
├── span_correlator.py    # Span 关联器
├── span_exporter.py      # 导出器 (JSON, Markdown, Chrome Tracing)
├── span_trace_main.py    # 命令行入口
├── DESIGN.md             # 详细设计文档
└── README.md             # 本文件
```

## 🔧 命令行选项

```bash
python span_trace_main.py [OPTIONS] [ID]

选项:
  ID                        Session ID (s-xxx) 或 Conversation ID (UUID)
  --input, -i FILE         从文件读取日志
  --conversation-id ID     指定 Conversation ID (用于 --input)
  --session-id ID          指定 Session ID (可选)
  --output, -o DIR         输出目录
  --last, -l RANGE         Kibana 时间范围 (默认: 21d)
  --formats, -f FORMATS    导出格式 (json/timeline/markdown/chrome_tracing)

示例:
  python span_trace_main.py s-abc123
  python span_trace_main.py c7b8b6fe-...
  python span_trace_main.py --input logs.json --conversation-id c7b8b6fe-...
  python span_trace_main.py s-abc123 --formats json markdown
```

## 🚀 高级用法

### 自定义 Span 提取

```python
from extractors.iva.span import SpanExtractor

extractor = SpanExtractor(trace_id="c7b8b6fe-...", session_id="s-abc123")
spans = extractor.extract_from_logs(logs)

# 访问未配对的 start 事件
print(f"Pending starts: {len(extractor.pending_starts)}")

# 访问孤立事件
print(f"Orphan events: {len(extractor.orphan_events)}")
```

### 自定义关联策略

```python
from extractors.iva.span import SpanCorrelator

# 调整时间容差
correlator = SpanCorrelator(time_tolerance_ms=200)
trace = correlator.correlate(spans)
```

### 自定义导出格式

```python
from extractors.iva.span import SpanExporter

class CustomExporter(SpanExporter):
    def export(self, trace):
        # 自定义导出逻辑
        return custom_format_data
```

## 📚 相关文档

- [DESIGN.md](./DESIGN.md) - 详细设计文档
- [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/)
- [Chrome Tracing Format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/)

## 🤝 贡献

欢迎贡献！请查看 [DESIGN.md](./DESIGN.md#贡献指南) 了解如何:
- 添加新的 Span 类型
- 添加新的导出格式
- 改进关联算法

## 📝 许可

MIT License
