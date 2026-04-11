#!/usr/bin/env python3
"""
IVA Timeline Converter - 将Turn数据转换为树形时间线结构

将扁平的 component_timeline 转换为层级化的树形结构，
以便使用树形时间线渲染器进行可视化。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

# 使用 models.parse_timestamp (它會委託給共享模組)
from .models import parse_timestamp

# 事件类型映射
EVENT_TYPE_MAP = {
    'grpc_send': 'gRPC Send',
    'first_response': 'First Response',
    'response_end': 'Response End',
    'interruption': 'User Interruption',
    'tool_call': 'Tool Call',
    'tool_call_start': 'Tool Call Start',
    'tool_call_end': 'Tool Call End',
    'llm_request': 'LLM Request',
    'llm_request_start': 'LLM Request Start',
    'llm_request_end': 'LLM Request End',
    'generation': 'Generation',
    'generation_start': 'Generation Start',
    'generation_end': 'Generation End',
    'agent_service_call': 'Agent Service Call',
    'agent_service_call_start': 'Agent Service Call Start',
    'agent_service_call_end': 'Agent Service Response',
    'error': 'Error',
}

# 组件显示名称
COMPONENT_DISPLAY_NAMES = {
    'assistant_runtime': '🎙️ Assistant Runtime',
    'nca': '🧠 NCA',
    'gmg': '⚡ GMG',
    'aig': '🔧 AIG',
    'agent_service': '🤖 Agent Service',
}

# 组件类型映射
COMPONENT_TYPE_MAP = {
    'assistant_runtime': 'SPAN',
    'nca': 'SPAN',
    'gmg': 'GENERATION',
    'aig': 'SPAN',
    'agent_service': 'SPAN',
}

# 组件别名映射 (标准化组件名)
COMPONENT_ALIAS_MAP = {
    'AR': 'assistant_runtime',
    'FSM': 'assistant_runtime',
    'STT': 'assistant_runtime',
    'TTS': 'assistant_runtime',
    'Agent': 'assistant_runtime',
    'Tool': 'assistant_runtime',
    'Runtime': 'assistant_runtime',
    'LLM': 'assistant_runtime',
    'AS': 'agent_service',
    'AS_v2': 'agent_service',
    'gm_gateway': 'gmg', 
    # Note: GMG is separate from NCA. Cross-component pairing handles start/end matching.
}

# 组件排序顺序 (显示顺序)
COMPONENT_SORT_ORDER = [
    'assistant_runtime',
    'agent_service',
    'nca',
    'aig',
    'gmg',
]


def convert_turn_to_tree(turn: 'Turn', turn_index: int = 0, session_start_ts: Optional[datetime] = None) -> Dict[str, Any]:
    """
    将Turn转换为树形时间线数据结构
    
    Args:
        turn: Turn对象
        turn_index: Turn索引(从0开始)
        session_start_ts: 会话开始时间，如果提供，则所有相对时间都是相对于此时间
        
    Returns:
        树形时间线数据字典
    """
    # 解析时间戳 - 使用頂層導入的 parse_timestamp
    start_ts = parse_timestamp(turn.start_timestamp) if turn.start_timestamp else None
    end_ts = parse_timestamp(turn.end_timestamp) if turn.end_timestamp else None
    
    if not start_ts or not end_ts:
        return None
    
    # 计算基准时间(毫秒)
    if session_start_ts:
        base_ms = session_start_ts.timestamp() * 1000
    else:
        base_ms = start_ts.timestamp() * 1000

    start_ms = (start_ts.timestamp() * 1000) - base_ms
    end_ms = (end_ts.timestamp() * 1000) - base_ms
    duration_ms = (end_ts.timestamp() - start_ts.timestamp()) * 1000
    
    # 构建Turn标题
    turn_title = f"Turn {turn.turn_number}"
    if turn.user_transcript:
        # 截取前30个字符
        transcript_preview = turn.user_transcript[:30]
        if len(turn.user_transcript) > 30:
            transcript_preview += "..."
        turn_title += f": {transcript_preview}"
    
    # 重要：先进行全局配对，再按组件分组
    # 这样 NCA 的 llm_request_start 可以配对 GMG 的 generation_end
    paired_timeline = _pair_events_globally(turn.component_timeline, base_ms)
    
    # 按组件分组事件
    component_events = _group_events_by_component(paired_timeline, base_ms)
    
    # 构建子节点(组件)
    children = []
    for component_name, events in component_events.items():
        if not events:
            continue
            
        component_node = _build_component_node(
            component_name, 
            events, 
            turn_index,
            duration_ms
        )
        if component_node:
            children.append(component_node)
            
    # 对子节点(组件)进行排序
    def get_sort_key(node):
        comp_name = node['data']['component']
        if comp_name in COMPONENT_SORT_ORDER:
            return COMPONENT_SORT_ORDER.index(comp_name)
        return 999  # 未知组件排在最后

    children.sort(key=get_sort_key)
    
    # 构建Turn节点
    turn_node = {
        'id': f'turn-{turn_index}',
        'name': turn_title,
        'type': 'TRACE',
        'start_ms': start_ms,
        'end_ms': end_ms,
        'children': children,
        'data': {
            'turn_number': turn.turn_number,
            'user_transcript': turn.user_transcript or '',
            'ai_response': turn.ai_response or '',
            'duration_ms': turn.duration_ms,
            'ttft_ms': turn.ttft_ms,
        }
    }
    
    return turn_node


def _pair_events_globally(component_timeline: List[Dict], base_ms: float) -> List[Dict]:
    """
    全局配对事件 - 跨组件配对 Start/End 事件
    
    在分组之前运行，允许 NCA 的 llm_request_start 配对 GMG 的 generation_end
    """
    from .event_pairing import pair_events

    if not component_timeline:
        return component_timeline

    # 先计算 relative_ms - 使用頂層導入的 parse_timestamp
    events_with_ms = []
    for event in component_timeline:
        event_copy = event.copy()
        ts = parse_timestamp(event.get('timestamp', ''))
        if ts:
            event_copy['relative_ms'] = (ts.timestamp() * 1000) - base_ms
        else:
            event_copy['relative_ms'] = event.get('offset_ms', 0)
        events_with_ms.append(event_copy)
    
    # 按时间排序
    events_with_ms.sort(key=lambda x: x.get('relative_ms', 0))
    
    # 使用 'nca' 规则进行全局配对(启用跨类型关闭)
    paired = pair_events(events_with_ms, 'nca')
    
    return paired



def _group_events_by_component(component_timeline: List[Dict], base_ms: float) -> Dict[str, List[Dict]]:
    """
    按组件分组事件
    
    Args:
        component_timeline: 组件时间线事件列表
        base_ms: 基准时间(毫秒)，所有相对时间将相对于此基准计算
        
    Returns:
        按组件分组的事件字典
    """
    grouped = {}

    # 使用頂層導入的 parse_timestamp
    for event in component_timeline:
        raw_component = event.get('component', 'unknown')
        # Normalize component name
        component = COMPONENT_ALIAS_MAP.get(raw_component, raw_component)
        # Also try lowercase
        if component not in COMPONENT_SORT_ORDER and raw_component.lower() in COMPONENT_SORT_ORDER:
             component = raw_component.lower()

        if component not in grouped:
            grouped[component] = []
        
        # 转换时间戳为相对毫秒
        event_copy = event.copy()
        if 'timestamp' in event:
            ts = parse_timestamp(event['timestamp'])
            if ts:
                event_copy['relative_ms'] = (ts.timestamp() * 1000) - base_ms
        elif 'duration_from_turn_start_ms' in event:
            # 如果是只有相对于turn start的时间，我们需要加上turn相对于base_ms的偏移
            # 但这里我们假设如果提供了 base_ms (session start)，调用者应该处理这种情况，
            # 或者我们在这里根本无法处理，因为我们不知道这个 event 所属的 turn start 是多少
            # 实际上，component_timeline 里的 events 通常有绝对时间戳
            # 如果只有相对时间，这在统一时间线模式下可能不准确
            event_copy['relative_ms'] = event['duration_from_turn_start_ms']
        
        grouped[component].append(event_copy)
    
    return grouped


def _build_component_node(component_name: str, events: List[Dict], 
                          turn_index: int, turn_duration_ms: float) -> Optional[Dict]:
    """
    构建组件节点
    
    Args:
        component_name: 组件名称
        events: 组件事件列表
        turn_index: Turn索引
        turn_duration_ms: Turn总时长
        
    Returns:
        组件节点字典
    """
    if not events:
        return None
    
    # 计算组件的开始和结束时间
    # 先按时间排序事件
    events.sort(key=lambda x: x.get('relative_ms', x.get('start_ms', 0)))
    
    # 注意: pairing 已在 _pair_events_globally 中完成
    # 这里不需要再次配对
    
    event_times = []
    for e in events:
        if 'start_ms' in e:
            event_times.append(e['start_ms'])
        if 'end_ms' in e:
            event_times.append(e['end_ms'])
        if 'relative_ms' in e:
            event_times.append(e['relative_ms'])
            
    if not event_times:
        return None
    
    start_ms = min(event_times)
    end_ms = max(event_times)
    
    # 如果只有一个事件点，给它一个小的持续时间
    if start_ms == end_ms:
        end_ms = start_ms + 10
    
    # 构建事件子节点
    children = []
    for i, event in enumerate(events):
        event_node = _build_event_node(event, component_name, turn_index, i)
        if event_node:
            children.append(event_node)
    
    # 获取组件显示名称和类型
    display_name = COMPONENT_DISPLAY_NAMES.get(component_name, component_name)
    node_type = COMPONENT_TYPE_MAP.get(component_name, 'SPAN')
    
    component_node = {
        'id': f'turn-{turn_index}-{component_name}',
        'name': display_name,
        'type': node_type,
        'start_ms': start_ms,
        'end_ms': end_ms,
        'children': children,
        'data': {
            'component': component_name,
            'event_count': len(events)
        }
    }
    
    return component_node


def _build_event_node(event: Dict, component_name: str,
                     turn_index: int, event_index: int) -> Optional[Dict]:
    """
    构建事件节点
    
    Args:
        event: 事件字典
        component_name: 组件名称
        turn_index: Turn索引
        event_index: 事件索引
        
    Returns:
        事件节点字典
    """
    relative_ms = event.get('relative_ms')
    start_ms = event.get('start_ms')
    
    if relative_ms is None and start_ms is None:
        return None
        
    is_span = event.get('is_span', False)
    if is_span:
        node_start = start_ms
        node_end = event.get('end_ms', start_ms + 1)
        node_type = 'SPAN'
    else:
        node_start = relative_ms
        node_end = relative_ms + 1
        node_type = 'POINT'
    
    event_type = event.get('event', 'unknown')
    event_name = EVENT_TYPE_MAP.get(event_type, event_type)
    
    # 如果有额外的元数据 detail, 添加到显示名称中
    meta = event.get('meta', {})
    extra_detail = meta.get('extra_detail', '') if meta else ''
    
    if extra_detail:
        event_name += extra_detail

    # Determine custom CSS class based on content
    custom_class = None
    detail_lower = extra_detail.lower()
    if '[filler-phrase]' in detail_lower or '[filler]' in detail_lower:
        custom_class = 'llm-filler'
    elif '[agent]' in detail_lower:
        custom_class = 'llm-agent'
    elif '[chitchat]' in detail_lower:
        custom_class = 'llm-chitchat'
    elif '[intent-analyzer]' in detail_lower or '[intent]' in detail_lower:
        custom_class = 'llm-intent'
        
    correlation_id = None
    if custom_class:
        # Create a simpler correlation ID for linking related events
        # Note: In span mode, the start/end are already merged, so highlighting related generic events
        # might still be useful if there are other related events (e.g. tool calls triggered by this LLM)
        correlation_id = f"turn-{turn_index}-linked-{custom_class}"

    event_node = {
        'id': f'turn-{turn_index}-{component_name}-event-{event_index}',
        'name': event_name,
        'type': node_type,
        'start_ms': node_start,
        'end_ms': node_end,
        'children': [], # Events don't have children in this model
        'data': event,
        'customClass': custom_class,
        'correlationId': correlation_id
    }
    
    return event_node


def convert_call_session_to_tree(turns: List['Turn']) -> List[Dict[str, Any]]:
    """
    将整个通话会话的所有Turn转换为树形时间线数据(列表形式)
    Deprecated: Prefer convert_session_to_unified_tree
    
    Args:
        turns: Turn对象列表
        
    Returns:
        树形时间线数据列表(每个Turn一个)
    """
    tree_data = []
    
    for i, turn in enumerate(turns):
        turn_tree = convert_turn_to_tree(turn, i)
        if turn_tree:
            tree_data.append(turn_tree)
    
    return tree_data


def convert_session_to_unified_tree(turns: List['Turn'], session_id: str = "Unknown Session") -> Dict[str, Any]:
    """
    将整个通话会话的所有Turn转换为单个统一的树形时间线数据
    
    Args:
        turns: Turn对象列表
        session_id: 会话ID
        
    Returns:
        统一的树形时间线数据字典
    """
    if not turns:
        return None
        
    # Try relative import first, fall back to absolute
    # 使用頂層導入的 parse_timestamp
    # 找到会话开始时间 (第一个Turn的开始时间)
    session_start_ts = None
    for turn in turns:
        ts = parse_timestamp(turn.start_timestamp)
        if ts:
            if session_start_ts is None or ts < session_start_ts:
                session_start_ts = ts
    
    if not session_start_ts:
        return None
        
    # 构建所有Turn节点
    turn_nodes = []
    
    for i, turn in enumerate(turns):
        turn_tree = convert_turn_to_tree(turn, i + 1, session_start_ts)
        if turn_tree:
            turn_nodes.append(turn_tree)
            
    # 计算总持续时间
    end_ms = 0
    if turn_nodes:
        end_ms = max(node['end_ms'] for node in turn_nodes)
        
    # 构建根节点
    root_node = {
        'id': 'session-root',
        'name': f'Start Session: {session_id}',
        'type': 'ROOT',
        'start_ms': 0,
        'end_ms': end_ms,
        'children': turn_nodes,
        'data': {
            'session_id': session_id,
            'turn_count': len(turns)
        }
    }
    
    return root_node


def get_component_summary(turn: 'Turn') -> Dict[str, Any]:
    """
    获取Turn中各组件的汇总信息
    
    Args:
        turn: Turn对象
        
    Returns:
        组件汇总字典
    """
    summary = {}
    
    for event in turn.component_timeline:
        component = event.get('component', 'unknown')
        if component not in summary:
            summary[component] = {
                'event_count': 0,
                'events': []
            }
        
        summary[component]['event_count'] += 1
        summary[component]['events'].append(event.get('event', 'unknown'))
    
    return summary
