#!/usr/bin/env python3
"""
Event Registry - Unified event definitions for extraction and pairing

This module serves as the single source of truth for:
1. Event extraction patterns (regex + component)
2. Event pairing rules (start/end matching, cross-type closers)
3. Detail extractors (for pairing_key generation and enrichment)

Usage:
    from .event_registry import EVENT_REGISTRY, get_patterns_for_component
    from .event_registry import extract_event_details, enrich_event
"""

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

# ==============================================================================
# Detail Extractor Functions
# ==============================================================================

def _extract_gmg_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取 GMG LLM 請求詳情"""
    details = {}

    # 從日誌字段提取
    if log.get('request_latency'):
        details['request_latency_ms'] = log['request_latency']
    if log.get('llm_1st_chunk_ms'):
        details['llm_1st_chunk_ms'] = log['llm_1st_chunk_ms']
    if log.get('model'):
        details['model'] = log['model']
    if log.get('total_tokens'):
        details['total_tokens'] = log['total_tokens']
    if log.get('prompt_tokens'):
        details['prompt_tokens'] = log['prompt_tokens']
    if log.get('completion_tokens'):
        details['completion_tokens'] = log['completion_tokens']

    return details


def _extract_tool_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取工具調用詳情"""
    details = {}

    # 從 message 提取工具名
    match = re.search(r'tool["\s:=]+["\']?(\w+)', message, re.IGNORECASE)
    if match:
        details['tool_name'] = match.group(1)

    # 嘗試其他模式
    if 'tool_name' not in details:
        match = re.search(r'(clientTool|serverTool)["\s:=]+["\']?(\w+)', message)
        if match:
            details['tool_type'] = match.group(1)
            details['tool_name'] = match.group(2)

    return details


def _extract_user_input_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取用戶輸入詳情"""
    details = {}

    match = re.search(r'"transcript"\s*:\s*"([^"]*)"', message)
    if match:
        details['transcript'] = match.group(1)[:100]

    return details


def _extract_phrase_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取 AI 回覆詳情"""
    details = {}

    match = re.search(r'Saying phrase:\s*(.+)$', message)
    if match:
        details['phrase'] = match.group(1)[:100]

    return details


def _extract_state_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取狀態變更詳情"""
    details = {}

    match = re.search(r'\[state:\s*(\w+(?:-\w+)*)\]', message)
    if match:
        details['state'] = match.group(1)

    return details


def _extract_llm_client_details(message: str, log: Dict[str, Any]) -> Dict[str, Any]:
    """提取 LLM Client 類型詳情 (chitchat, filler, etc.)"""
    details = {}

    match = re.search(r'\[GMG Client\]\[([\w-]+)\]', message)
    if match:
        details['llm_type'] = match.group(1)
        details['pairing_key'] = match.group(1)

    return details


# ==============================================================================
# Event Registry - Single Source of Truth
# ==============================================================================

EVENT_REGISTRY = {
    # ========== LLM Request ==========
    'llm_request': {
        'display_name': 'LLM Request',
        'start': {
            'patterns': [
                # NCA patterns
                (r'\[GMG Client\]\[.+\]', 'nca'),
                (r'(request|send)\s+model', 'nca'),
                # GMG patterns
                (r'(Request|request).*(start|begin|received)', 'gmg'),
                (r'(Sending|sending|forward).*(request|LLM|model)', 'gmg'),
            ],
        },
        'end': {
            'patterns': [
                # NCA patterns
                (r'(LLM|llm).*(response|complete|finish|end)', 'nca'),
                # GMG patterns
                (r'Request completed', 'gmg'),
                (r'(Request|request).*(complete|finish|end)', 'gmg'),
                (r'request_latency', 'gmg'),
            ],
        },
        'detail_extractor': r'\[GMG Client\]\[([\w-]+)\]',  # Extract: chitchat, filler, etc.
        'closers': ['generation'],  # generation_end can close llm_request
    },

    # ========== Generation ==========
    'generation': {
        'display_name': 'Generation',
        'start': {
            'patterns': [
                # NCA patterns
                (r'(Generat|generat).*(start|begin)', 'nca'),
                (r'(Start|start).*(generat|response)', 'nca'),
                # GMG patterns
                (r'(Generat|generat).*(start|begin)', 'gmg'),
                (r'(first|First).*(token|chunk)', 'gmg'),
            ],
        },
        'end': {
            'patterns': [
                # NCA patterns
                (r'(Generat|generat).*(end|complete|finish)', 'nca'),
                (r'(response|generation).*(complete|finish|end)', 'nca'),
                # GMG patterns
                (r'(Generat|generat).*(end|complete|finish)', 'gmg'),
                (r'(Stream|stream).*(end|complete|finish)', 'gmg'),
            ],
        },
        'detail_extractor': r'\[GMG Client\]\[([\w-]+)\]',
        'closers': ['llm_request'],  # llm_request_end can close generation
    },

    # ========== Tool Call ==========
    'tool_call': {
        'display_name': 'Tool Call',
        'start': {
            'patterns': [
                # AR patterns
                (r'"type"\s*:\s*"tool"', 'assistant_runtime'),
                (r'Calling (client |server )?tool', 'assistant_runtime'),
                (r'(clientTool|serverTool)\s*[:=]', 'assistant_runtime'),
                # NCA patterns
                (r'(Calling|calling).*(tool|Tool)', 'nca'),
                (r'(clientTool|serverTool)', 'nca'),
                # AIG patterns
                (r'(Calling|calling).*(tool|Tool)', 'aig'),
                # Agent Service patterns
                (r'(Calling|calling).*(tool|Tool)', 'agent_service'),
                (r'(clientTool|serverTool)', 'agent_service'),
            ],
        },
        'end': {
            'patterns': [
                # AR patterns
                (r'Received toolResult', 'assistant_runtime'),
                (r'(Client |Server )?[Tt]ool completed', 'assistant_runtime'),
                # NCA patterns
                (r'(tool|Tool).*(completed|finished|result|response)', 'nca'),
                # AIG patterns
                (r'(tool|Tool).*(completed|finished|result|response)', 'aig'),
                # Agent Service patterns
                (r'(tool|Tool).*(completed|finished|result|response)', 'agent_service'),
            ],
        },
        'closers': [],
    },

    # ========== Agent Service Call ==========
    'agent_service_call': {
        'display_name': 'Agent Service Call',
        'start': {
            'patterns': [
                (r'(Calling|calling|request).*(agent|Agent)', 'aig'),
            ],
        },
        'end': {
            'patterns': [
                (r'(agent|Agent).*(response|complete|finish)', 'aig'),
            ],
        },
        'closers': [],
    },

    # ========== TTS Synthesis ==========
    'tts_synthesis': {
        'display_name': 'TTS Synthesis',
        'start': {
            'patterns': [
                (r'new generate request session_id', 'cprc_sgs'),
                (r'synthesis started', 'cprc_sgs'),
            ],
        },
        'end': {
            'patterns': [
                (r'synthesis finished', 'cprc_sgs'),
                (r'audio end session_id', 'cprc_sgs'),
            ],
        },
        'closers': [],
    },

    # ========== TTS Playback ==========
    'tts_playback': {
        'display_name': 'TTS Playback',
        'start': {
            'patterns': [
                (r'first chunk received latency', 'cprc_sgs'),
            ],
        },
        'end': {
            'patterns': [
                (r'playback finished audio_duration', 'cprc_sgs'),
            ],
        },
        'closers': [],
    },

    # ========== Session Create ==========
    'session_create': {
        'display_name': 'Session Create',
        'start': {
            'patterns': [
                (r'Start processing task', 'assistant_runtime'),
                (r'Creating Nova conversation', 'assistant_runtime'),
            ],
        },
        'end': {
            'patterns': [
                (r'Nova Conversation is created', 'assistant_runtime'),
                (r'Created new Conversation', 'assistant_runtime'),
            ],
        },
        'closers': [],
    },

    # ========== ASR Session ==========
    'asr_session': {
        'display_name': 'ASR Session',
        'start': {
            'patterns': [
                (r'POST /v1/session/', 'cprc_srs'),
                (r'Configuring meeting transcript', 'cprc_srs'),
            ],
        },
        'end': {
            'patterns': [
                (r'SDP answer accepted', 'cprc_srs'),
                (r'start transcription', 'cprc_srs'),
            ],
        },
        'closers': [],
    },

    # ========== ASR Recognition ==========
    'asr_recognition': {
        'display_name': 'ASR Recognition',
        'start': {
            'patterns': [
                (r'Connecting to Google API', 'cprc_srs'),
                (r'Processing stream started', 'cprc_srs'),
            ],
        },
        'end': {
            'patterns': [
                (r'asr_latency=', 'cprc_srs'),
            ],
        },
        'closers': [],
    },

    # ========== Greeting ==========
    'greeting': {
        'display_name': 'Greeting',
        'start': {
            'patterns': [
                (r'\[state: greeting\] Generating greeting', 'assistant_runtime'),
            ],
        },
        'end': {
            'patterns': [
                (r'\[state: greeting\] Phrase has been spoken', 'assistant_runtime'),
                (r'\[state: greeting\] All phrases has been spoken', 'assistant_runtime'),
            ],
        },
        'closers': [],
    },

    # ========== Answering ==========
    'answering': {
        'display_name': 'Answering',
        'start': {
            'patterns': [
                (r'\[state: answering\] Generating response', 'assistant_runtime'),
                (r'\[state: listening\] Received transcript from user', 'assistant_runtime'),
            ],
        },
        'end': {
            'patterns': [
                (r'\[state: answering\] Phrase has been spoken', 'assistant_runtime'),
            ],
        },
        'closers': [],
    },

    # ========== Filler Generation ==========
    'filler': {
        'display_name': 'Filler',
        'start': {
            'patterns': [
                (r'\[FILLER\] Generating initial filler phrase', 'nca'),
                (r'Filler flow started', 'nca'),
            ],
        },
        'end': {
            'patterns': [
                (r'\[FILLER\] filler generation completed', 'nca'),
                (r'Filler drained', 'nca'),
            ],
        },
        'closers': [],
    },

    # ========== Intent Analyzer ==========
    'intent_analyzer': {
        'display_name': 'Intent Analyzer',
        'start': {
            'patterns': [
                (r'Intent analyzer starting', 'nca'),
                (r'\[GMG Client\]\[intent-analyzer\]', 'nca'),
            ],
        },
        'end': {
            'patterns': [
                (r'Intent Analyzer Response Duration', 'nca'),
                (r'Intent analyzer.*completed', 'nca'),
            ],
        },
        'closers': [],
    },

    # ========== Agent Processing ==========
    'agent_processing': {
        'display_name': 'Agent Processing',
        'start': {
            'patterns': [
                (r'\[Agent\]\[.*\]\[DYNAMIC_ACTION\] Agent running started', 'nca'),
                (r'Starting agent processing', 'nca'),
            ],
        },
        'end': {
            'patterns': [
                (r'RequestAnalyzer completed with', 'nca'),
                (r'\[Agent\].*completed', 'nca'),
            ],
        },
        'closers': [],
    },

    # ========== AIG Tool Call ==========
    'aig_tool_call': {
        'display_name': 'AIG Tool Call',
        'start': {
            'patterns': [
                (r'Tool call request context', 'aig'),
                (r'Start exchanging request', 'aig'),
            ],
        },
        'end': {
            'patterns': [
                (r'Completed exchanging request', 'aig'),
            ],
        },
        'closers': [],
    },

    # ========== Knowledge Base Query ==========
    'kb_query': {
        'display_name': 'KB Query',
        'start': {
            'patterns': [
                (r'Start handling get.*/tools/knowledge-base', 'agent_service'),
                (r'Tool request started', 'agent_service'),
            ],
        },
        'end': {
            'patterns': [
                (r'Tool executed in', 'agent_service'),
                (r'knowledge_base request completed', 'agent_service'),
            ],
        },
        'closers': [],
    },

    # ========== Chitchat Flow ==========
    'chitchat': {
        'display_name': 'Chitchat',
        'start': {
            'patterns': [
                (r'Chitchat flow started', 'nca'),
                (r'\[GMG Client\]\[chitchat\]', 'nca'),
            ],
        },
        'end': {
            'patterns': [
                (r'Chitchat generation completed', 'nca'),
            ],
        },
        'closers': [],
    },

    # ========== Standalone Events (no pairing) ==========
    'grpc_send': {
        'display_name': 'gRPC Send',
        'standalone': {
            'patterns': [
                (r'Sending (init |generation )?request', 'assistant_runtime'),
                (r'Generating response for:', 'assistant_runtime'),
            ],
        },
    },

    'first_response': {
        'display_name': 'First Response',
        'standalone': {
            'patterns': [
                (r'Saying phrase:', 'assistant_runtime'),
            ],
        },
    },

    'response_end': {
        'display_name': 'Response End',
        'standalone': {
            'patterns': [
                (r'LLM generation has finished', 'assistant_runtime'),
                (r'LLM generation and speaking has been completed', 'assistant_runtime'),
            ],
        },
    },

    'interruption': {
        'display_name': 'User Interruption',
        'standalone': {
            'patterns': [
                (r'Interrupt(ing|ed) the generation', 'assistant_runtime'),
                (r'User interrupt', 'assistant_runtime'),
            ],
        },
    },

    'error': {
        'display_name': 'Error',
        'standalone': {
            'patterns': [
                (r'(ERROR|Error|error)', 'nca'),
                (r'(ERROR|Error|error)', 'aig'),
                (r'(ERROR|Error|error)', 'gmg'),
                (r'(ERROR|Error|error)', 'agent_service'),
            ],
        },
    },

    # ========== AR Specific Events (from ai_extractor) ==========
    'user_input': {
        'display_name': 'User Input',
        'standalone': {
            'patterns': [
                (r'Received transcript from user', 'assistant_runtime'),
            ],
        },
        'detail_func': _extract_user_input_details,
    },

    'state_change': {
        'display_name': 'State Change',
        'standalone': {
            'patterns': [
                (r'\[state:\s*(\w+(?:-\w+)*)\]', 'assistant_runtime'),
            ],
        },
        'detail_func': _extract_state_details,
    },

    'user_connected': {
        'display_name': 'User Connected',
        'standalone': {
            'patterns': [
                (r'User connected', 'assistant_runtime'),
            ],
        },
    },

    'conversation_close': {
        'display_name': 'Conversation Close',
        'standalone': {
            'patterns': [
                (r'Conversation close', 'assistant_runtime'),
            ],
        },
    },

    'llm_finished': {
        'display_name': 'LLM Finished',
        'standalone': {
            'patterns': [
                (r'LLM generation has finished', 'assistant_runtime'),
            ],
        },
    },

    'turn_complete': {
        'display_name': 'Turn Complete',
        'standalone': {
            'patterns': [
                (r'LLM generation and speaking has been completed', 'assistant_runtime'),
            ],
        },
    },

    # ========== NCA Specific Events ==========
    'context_completed': {
        'display_name': 'Context Completed',
        'standalone': {
            'patterns': [
                (r'Context completed', 'nca'),
            ],
        },
    },

    # ========== GMG Specific Events ==========
    'first_token': {
        'display_name': 'First Token',
        'standalone': {
            'patterns': [
                (r'(first|First).*(token|chunk)', 'gmg'),
            ],
        },
        'detail_func': _extract_gmg_details,
    },

    'stream_end': {
        'display_name': 'Stream End',
        'standalone': {
            'patterns': [
                (r'(Stream|stream).*(end|complete|finish)', 'gmg'),
            ],
        },
    },

    # ========== CPRC SRS (Speech Recognition) ==========
    'recognition_start': {
        'display_name': 'Recognition Start',
        'standalone': {
            'patterns': [
                (r'Recognition started', 'cprc_srs'),
            ],
        },
    },

    'recognition_end': {
        'display_name': 'Recognition End',
        'standalone': {
            'patterns': [
                (r'Recognition (ended|completed)', 'cprc_srs'),
            ],
        },
    },

    'final_result': {
        'display_name': 'Final Result',
        'standalone': {
            'patterns': [
                (r'Final result', 'cprc_srs'),
            ],
        },
    },

    # ========== CPRC SGS (Speech Synthesis) ==========
    'synthesis_start': {
        'display_name': 'Synthesis Start',
        'standalone': {
            'patterns': [
                (r'Synthesis started', 'cprc_sgs'),
            ],
        },
    },

    'synthesis_end': {
        'display_name': 'Synthesis End',
        'standalone': {
            'patterns': [
                (r'Synthesis (ended|completed)', 'cprc_sgs'),
            ],
        },
    },

    'audio_chunk': {
        'display_name': 'Audio Chunk',
        'standalone': {
            'patterns': [
                (r'Audio chunk', 'cprc_sgs'),
            ],
        },
    },
}

# Event type to detail extractor function mapping
EVENT_DETAIL_EXTRACTORS: Dict[str, Callable[[str, Dict[str, Any]], Dict[str, Any]]] = {
    'llm_request_start': _extract_llm_client_details,
    'llm_request_end': _extract_gmg_details,
    'generation_start': _extract_llm_client_details,
    'generation_end': _extract_gmg_details,
    'tool_call_start': _extract_tool_details,
    'tool_call_end': _extract_tool_details,
    'user_input': _extract_user_input_details,
    'first_response': _extract_phrase_details,
    'state_change': _extract_state_details,
    'first_token': _extract_gmg_details,
}


# ==============================================================================
# Helper Functions
# ==============================================================================

def get_patterns_for_component(component: str) -> List[Tuple[str, str]]:
    """
    Get all extraction patterns for a specific component.
    
    Returns:
        List of (regex_pattern, event_name) tuples
    """
    patterns = []
    component_lower = component.lower()
    
    # Map common aliases
    component_aliases = {
        'ar': 'assistant_runtime',
        'as': 'agent_service',
        'as_v2': 'agent_service',
    }
    component_key = component_aliases.get(component_lower, component_lower)
    
    for event_type, config in EVENT_REGISTRY.items():
        # Check start patterns
        if 'start' in config:
            for pattern, comp in config['start']['patterns']:
                if comp == component_key:
                    patterns.append((pattern, f"{event_type}_start"))
        
        # Check end patterns
        if 'end' in config:
            for pattern, comp in config['end']['patterns']:
                if comp == component_key:
                    patterns.append((pattern, f"{event_type}_end"))
        
        # Check standalone patterns
        if 'standalone' in config:
            for pattern, comp in config['standalone']['patterns']:
                if comp == component_key:
                    patterns.append((pattern, event_type))
    
    return patterns


def get_detail_extractor(event_type: str) -> Optional[str]:
    """Get the detail extractor regex for an event type."""
    base_type = event_type.replace('_start', '').replace('_end', '')
    config = EVENT_REGISTRY.get(base_type, {})
    return config.get('detail_extractor')


def build_event_config() -> Dict[str, Tuple[str, bool]]:
    """
    Build event config for pairing module.
    
    Returns:
        Dict mapping event names to (base_type, is_start) tuples
    """
    config = {}
    for event_type, event_config in EVENT_REGISTRY.items():
        if 'start' in event_config:
            config[f"{event_type}_start"] = (event_type, True)
        if 'end' in event_config:
            config[f"{event_type}_end"] = (event_type, False)
    return config


def build_close_map() -> Dict[str, List[str]]:
    """
    Build cross-type closure map from registry.

    Returns:
        Dict mapping base_type to list of types it can close
    """
    close_map = {}
    for event_type, config in EVENT_REGISTRY.items():
        closers = config.get('closers', [])
        if closers:
            close_map[event_type] = closers
    return close_map


def extract_event_details(
    event_type: str,
    message: str,
    log: Dict[str, Any]
) -> Dict[str, Any]:
    """
    使用對應的 detail_extractor 提取事件詳情

    Args:
        event_type: 事件類型 (如 'llm_request_start', 'tool_call_end')
        message: 日誌消息
        log: 原始日誌字典

    Returns:
        提取的詳情字典
    """
    # 先嘗試精確匹配
    extractor = EVENT_DETAIL_EXTRACTORS.get(event_type)

    # 如果沒找到，嘗試 base_type
    if not extractor:
        base_type = event_type.replace('_start', '').replace('_end', '')
        config = EVENT_REGISTRY.get(base_type, {})
        extractor = config.get('detail_func')

    if extractor:
        return extractor(message, log)

    return {}


def enrich_event(
    event: Dict[str, Any],
    log: Dict[str, Any]
) -> Dict[str, Any]:
    """
    豐富事件信息，添加額外的上下文詳情

    Args:
        event: 事件字典 (需包含 event_type)
        log: 原始日誌字典

    Returns:
        豐富後的事件字典 (原地修改並返回)
    """
    event_type = event.get('event_type', '')
    message = log.get('message', '') or event.get('message', '')

    # 提取詳情
    details = extract_event_details(event_type, message, log)

    # 合併到事件
    event.update(details)

    return event


def match_event_type(
    message: str,
    component: str
) -> Optional[str]:
    """
    根據消息內容匹配事件類型

    Args:
        message: 日誌消息
        component: 組件名稱

    Returns:
        匹配的事件類型，或 None
    """
    patterns = get_patterns_for_component(component)

    for pattern, event_type in patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return event_type

    return None


def get_all_components() -> List[str]:
    """獲取所有已定義的組件列表"""
    components = set()

    for config in EVENT_REGISTRY.values():
        for section in ['start', 'end', 'standalone']:
            if section in config:
                for _, comp in config[section]['patterns']:
                    components.add(comp)

    return sorted(components)


def get_display_name(event_type: str) -> str:
    """獲取事件的顯示名稱"""
    base_type = event_type.replace('_start', '').replace('_end', '')
    config = EVENT_REGISTRY.get(base_type, {})

    display = config.get('display_name', event_type)

    if event_type.endswith('_start'):
        display += ' Start'
    elif event_type.endswith('_end'):
        display += ' End'

    return display
