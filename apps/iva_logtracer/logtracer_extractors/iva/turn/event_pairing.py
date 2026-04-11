#!/usr/bin/env python3
"""
Event Pairing Module - Pairs Start/End events into Span events

This module provides component-specific logic for pairing timeline events.
For example, an "LLM Request Start" event can be paired with an "LLM Request End"
event to create a single "LLM Request" span with actual duration.

Configuration is loaded from event_registry.py to ensure single source of truth.
"""

from typing import Dict, List

# Import configuration builders from registry
from .event_registry import build_close_map, build_event_config

# Build configuration from registry (single source of truth)
DEFAULT_EVENT_CONFIG = build_event_config()
DEFAULT_CLOSE_MAP = build_close_map()

# Component-specific pairing rules
# These now reference the registry-generated config
COMPONENT_PAIRING_RULES = {
    'default': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # No fallback closure by default
    },
    'nca': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': DEFAULT_CLOSE_MAP  # Use registry-defined closers
    },
    'gmg': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching
    },
    'assistant_runtime': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching
    },
    'cprc_srs': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching for ASR
    },
    'cprc_sgs': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching for TTS
    },
    'aig': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching
    },
    'agent_service': {
        'event_config': DEFAULT_EVENT_CONFIG,
        'close_map': {}  # Strict matching
    }
}


def get_component_key(component_name: str) -> str:
    """
    Normalize component name to rule lookup key.
    
    Args:
        component_name: Raw component name from timeline
        
    Returns:
        Normalized key for COMPONENT_PAIRING_RULES lookup
    """
    if not component_name:
        return 'default'
    
    normalized = component_name.lower()
    
    # Exact match first
    if normalized in COMPONENT_PAIRING_RULES:
        return normalized
    
    # Partial match fallback
    if 'nca' in normalized:
        return 'nca'
    elif 'gmg' in normalized:
        return 'gmg'
    elif 'assistant_runtime' in normalized or 'ar' in normalized:
        return 'assistant_runtime'
    elif 'cprc_srs' in normalized or 'srs' in normalized:
        return 'cprc_srs'
    elif 'cprc_sgs' in normalized or 'sgs' in normalized:
        return 'cprc_sgs'
    elif 'aig' in normalized:
        return 'aig'
    elif 'agent_service' in normalized or 'as' in normalized:
        return 'agent_service'
    
    return 'default'


def create_span(output_list: List[Dict], start_evt: Dict, end_evt: Dict, event_type: str) -> None:
    """
    Create a span event from start/end events and append to output list.
    
    Args:
        output_list: List to append the span to
        start_evt: The start event dict
        end_evt: The end event dict
        event_type: The unified event type name (e.g., 'llm_request')
    """
    span_evt = start_evt.copy()
    span_evt['end_ms'] = end_evt.get('relative_ms')
    span_evt['start_ms'] = start_evt.get('relative_ms')
    span_evt['is_span'] = True
    
    if 'relative_ms' in span_evt:
        del span_evt['relative_ms']
    
    span_evt['event'] = event_type
    
    output_list.append(span_evt)


def pair_events(events: List[Dict], component_name: str = '') -> List[Dict]:
    """
    Pair Start/End events into Span events using pairing_key for precise matching.
    
    This function processes a list of timeline events and attempts to pair
    matching start/end events into single span events with duration.
    
    Matching algorithm:
    1. Use pairing_key (e.g., 'llm_request:chitchat') for exact matching
    2. Fall back to base_type matching if pairing_key not available
    3. Apply cross-type closure rules for specific components (e.g., NCA)
    
    Args:
        events: List of event dicts, each with 'event', 'relative_ms', and optionally 'pairing_key'
        component_name: Name of the component for rule lookup
        
    Returns:
        List of events with paired start/end events converted to spans
    """
    if not events or len(events) < 2:
        return events

    # Get component-specific rules
    comp_key = get_component_key(component_name)
    rules = COMPONENT_PAIRING_RULES.get(comp_key, COMPONENT_PAIRING_RULES['default'])
    event_config = rules['event_config']
    close_map = rules['close_map']

    paired = []
    # Use pairing_key as primary key, with base_type fallback
    pending_starts: Dict[str, List[tuple]] = {}  # {pairing_key: [(event, index), ...]}
    processed_indices = set()
    
    for i, event in enumerate(events):
        evt_type = event.get('event', '')
        
        if evt_type in event_config:
            base_type, is_start = event_config[evt_type]
            
            # Get pairing_key from event, or use base_type as fallback
            pairing_key = event.get('pairing_key', base_type)
            
            if is_start:
                if pairing_key not in pending_starts:
                    pending_starts[pairing_key] = []
                pending_starts[pairing_key].append((event, i))
            else:
                # END EVENT
                matched = False
                
                # 1. Try exact pairing_key match first
                if pairing_key in pending_starts and pending_starts[pairing_key]:
                    start_evt, start_idx = pending_starts[pairing_key].pop()
                    create_span(paired, start_evt, event, base_type)
                    processed_indices.add(start_idx)
                    processed_indices.add(i)
                    matched = True
                
                # 2. Try base_type fallback if pairing_key didn't match
                if not matched and pairing_key != base_type:
                    if base_type in pending_starts and pending_starts[base_type]:
                        start_evt, start_idx = pending_starts[base_type].pop()
                        create_span(paired, start_evt, event, base_type)
                        processed_indices.add(start_idx)
                        processed_indices.add(i)
                        matched = True
                
                # 3. Try cross-type closure (for NCA: generation_end closes llm_request)
                if close_map and base_type in close_map:
                    for target_type in close_map[base_type]:
                        # Find all keys that start with target_type
                        keys_to_close = [k for k in pending_starts.keys() 
                                        if k == target_type or k.startswith(f"{target_type}:")]
                        for key in keys_to_close:
                            while pending_starts.get(key):
                                start_evt, start_idx = pending_starts[key].pop()
                                create_span(paired, start_evt, event, target_type)
                                processed_indices.add(start_idx)
                                processed_indices.add(i)
                            
    # Add unpaired events
    for i, event in enumerate(events):
        if i not in processed_indices:
            paired.append(event)
            
    # Sort by start time
    paired.sort(key=lambda e: e.get('start_ms', e.get('relative_ms', 0)))
    
    return paired
