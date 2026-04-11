"""
Turn Analysis API for IVA Log Tracer

Provides endpoints for analyzing conversation turns.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.iva_logtracer.logtracer_extractors.iva.orchestrator import SessionTraceOrchestrator

from .logtracer import get_client

router = APIRouter(prefix="/turn-analysis", tags=["turn-analysis"])


class TurnEvent(BaseModel):
    """Single event in a turn"""
    timestamp: str
    type: str  # 'asr', 'llm_request', 'llm_response', 'tool_call', 'tts', 'state_change'
    component: str
    message: str
    duration_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class Turn(BaseModel):
    """Single conversation turn"""
    turn_number: int
    start_time: str
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    user_input: Optional[str] = None
    bot_response: Optional[str] = None
    state: str
    events: List[TurnEvent] = []
    tools_called: List[str] = []
    errors: List[str] = []
    ttft_ms: Optional[int] = None  # Time to first token


class TurnAnalysisResponse(BaseModel):
    """Turn analysis result"""
    session_id: str
    conversation_id: Optional[str] = None
    total_turns: int
    total_duration_ms: Optional[int] = None
    turns: List[Turn]
    summary: Dict[str, Any]


class TurnAnalyzer:
    """
    Analyzes conversation turns from trace logs
    
    Parses logs to identify:
    - Turn boundaries (state transitions)
    - User inputs (transcript events)
    - Bot responses (TTS events)
    - Tool calls
    - Timing metrics (TTFT, latency)
    """
    
    # Patterns for parsing logs
    PATTERNS = {
        'state_change': re.compile(r'\[state:\s*(\w+)\]'),
        'transcript': re.compile(r'Received transcript from user[:\s]*(.*)'),
        'saying_phrase': re.compile(r'Saying phrase[:\s]*["\']?(.+?)["\']?\s*$'),
        'phrase_spoken': re.compile(r'Phrase has been spoken[:\s]*["\']?(.+?)["\']?\s*$'),
        'tool_call': re.compile(r'Calling client tool[:\s]*(\w+)'),
        'server_tool': re.compile(r'serverTool[:\s]*(\w+)'),
        'llm_request': re.compile(r'Sending request'),
        'llm_response': re.compile(r'Received (generate|end)'),
        'ttft': re.compile(r'Observed TTFT.*?:\s*(\d+)'),
        'error': re.compile(r'(error|failed|timeout)', re.IGNORECASE),
    }
    
    # States that indicate turn boundaries
    TURN_BOUNDARY_STATES = ['listening', 'answering', 'greeting', 'after-greeting']
    
    def __init__(self, logs: Dict[str, List[Dict[str, Any]]]):
        """
        Initialize analyzer with logs from trace
        
        Args:
            logs: Dictionary of component -> log entries
        """
        self.logs = logs
        self.all_logs = self._merge_and_sort_logs()
    
    def _merge_and_sort_logs(self) -> List[Dict[str, Any]]:
        """Merge logs from all components and sort by timestamp"""
        merged = []
        for component, entries in self.logs.items():
            for entry in entries:
                merged.append({
                    **entry,
                    '_component': component,
                })
        
        # Sort by timestamp
        merged.sort(key=lambda x: x.get('@timestamp', x.get('timestamp', '')))
        return merged
    
    def _parse_log_entry(self, log: Dict[str, Any]) -> Optional[TurnEvent]:
        """Parse a single log entry into a TurnEvent"""
        message = log.get('message', '')
        timestamp = log.get('@timestamp', log.get('timestamp', ''))
        component = log.get('_component', 'unknown')
        
        # Check for state change
        state_match = self.PATTERNS['state_change'].search(message)
        if state_match:
            return TurnEvent(
                timestamp=timestamp,
                type='state_change',
                component=component,
                message=message,
                metadata={'state': state_match.group(1)}
            )
        
        # Check for transcript
        transcript_match = self.PATTERNS['transcript'].search(message)
        if transcript_match:
            return TurnEvent(
                timestamp=timestamp,
                type='asr',
                component=component,
                message=transcript_match.group(1) or message,
            )
        
        # Check for saying phrase
        saying_match = self.PATTERNS['saying_phrase'].search(message)
        if saying_match:
            return TurnEvent(
                timestamp=timestamp,
                type='tts',
                component=component,
                message=saying_match.group(1) or message,
            )
        
        # Check for tool calls
        tool_match = self.PATTERNS['tool_call'].search(message) or self.PATTERNS['server_tool'].search(message)
        if tool_match:
            return TurnEvent(
                timestamp=timestamp,
                type='tool_call',
                component=component,
                message=message,
                metadata={'tool_name': tool_match.group(1)}
            )
        
        # Check for TTFT
        ttft_match = self.PATTERNS['ttft'].search(message)
        if ttft_match:
            return TurnEvent(
                timestamp=timestamp,
                type='ttft',
                component=component,
                message=message,
                duration_ms=int(ttft_match.group(1)),
            )
        
        # Check for error
        if self.PATTERNS['error'].search(message):
            return TurnEvent(
                timestamp=timestamp,
                type='error',
                component=component,
                message=message,
            )
        
        return None
    
    def _calculate_duration(self, start: str, end: str) -> Optional[int]:
        """Calculate duration in milliseconds between two timestamps"""
        try:
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            return int((end_dt - start_dt).total_seconds() * 1000)
        except:
            return None
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyze logs and extract turns
        
        Returns:
            Dictionary with turns and summary
        """
        turns: List[Turn] = []
        current_turn: Optional[Turn] = None
        turn_number = 0
        current_state = 'init'
        
        for log in self.all_logs:
            event = self._parse_log_entry(log)
            if not event:
                continue
            
            # Handle state changes
            if event.type == 'state_change':
                new_state = event.metadata.get('state', 'unknown')
                
                # Check if this is a turn boundary
                if new_state in ['answering'] and current_state in ['listening', 'after-greeting', 'greeting']:
                    # Start new turn
                    if current_turn:
                        current_turn.end_time = event.timestamp
                        if current_turn.start_time:
                            current_turn.duration_ms = self._calculate_duration(
                                current_turn.start_time, current_turn.end_time
                            )
                        turns.append(current_turn)
                    
                    turn_number += 1
                    current_turn = Turn(
                        turn_number=turn_number,
                        start_time=event.timestamp,
                        state=new_state,
                        events=[],
                        tools_called=[],
                        errors=[],
                    )
                
                current_state = new_state
            
            # Add event to current turn
            if current_turn:
                current_turn.events.append(event)
                
                # Extract specific data
                if event.type == 'asr':
                    current_turn.user_input = event.message
                elif event.type == 'tts' and not current_turn.bot_response:
                    current_turn.bot_response = event.message
                elif event.type == 'tool_call' and event.metadata:
                    current_turn.tools_called.append(event.metadata.get('tool_name', 'unknown'))
                elif event.type == 'error':
                    current_turn.errors.append(event.message)
                elif event.type == 'ttft':
                    current_turn.ttft_ms = event.duration_ms
        
        # Close last turn
        if current_turn:
            if self.all_logs:
                current_turn.end_time = self.all_logs[-1].get('@timestamp', self.all_logs[-1].get('timestamp'))
                if current_turn.start_time and current_turn.end_time:
                    current_turn.duration_ms = self._calculate_duration(
                        current_turn.start_time, current_turn.end_time
                    )
            turns.append(current_turn)
        
        # Calculate summary
        summary = self._calculate_summary(turns)
        
        return {
            'total_turns': len(turns),
            'turns': [t.model_dump() for t in turns],
            'summary': summary,
        }
    
    def _calculate_summary(self, turns: List[Turn]) -> Dict[str, Any]:
        """Calculate summary statistics"""
        if not turns:
            return {}
        
        total_duration = sum(t.duration_ms or 0 for t in turns)
        ttft_values = [t.ttft_ms for t in turns if t.ttft_ms]
        avg_ttft = sum(ttft_values) / len(ttft_values) if ttft_values else None
        
        all_tools = []
        for t in turns:
            all_tools.extend(t.tools_called)
        
        error_count = sum(len(t.errors) for t in turns)
        
        return {
            'total_duration_ms': total_duration,
            'avg_turn_duration_ms': total_duration / len(turns) if turns else 0,
            'avg_ttft_ms': avg_ttft,
            'total_tools_called': len(all_tools),
            'unique_tools': list(set(all_tools)),
            'error_count': error_count,
        }


@router.get("/sessions/{session_id}", response_model=TurnAnalysisResponse)
async def get_turn_analysis(session_id: str):
    """
    Analyze turns for a session
    
    Args:
        session_id: Session ID to analyze
        
    Returns:
        Turn analysis with timing metrics and events
    """
    client = get_client()
    orchestrator = SessionTraceOrchestrator(client)
    
    try:
        ctx = orchestrator.trace_by_session(session_id)
        analyzer = TurnAnalyzer(ctx.logs)
        result = analyzer.analyze()
        
        return TurnAnalysisResponse(
            session_id=session_id,
            conversation_id=ctx.conversation_id,
            total_turns=result['total_turns'],
            total_duration_ms=result['summary'].get('total_duration_ms'),
            turns=[Turn(**t) for t in result['turns']],
            summary=result['summary'],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}", response_model=TurnAnalysisResponse)
async def get_turn_analysis_by_conversation(conversation_id: str):
    """
    Analyze turns for a conversation
    
    Args:
        conversation_id: Conversation ID to analyze
        
    Returns:
        Turn analysis with timing metrics and events
    """
    client = get_client()
    orchestrator = SessionTraceOrchestrator(client)
    
    try:
        ctx = orchestrator.trace_by_conversation(conversation_id)
        analyzer = TurnAnalyzer(ctx.logs)
        result = analyzer.analyze()
        
        return TurnAnalysisResponse(
            session_id=ctx.session_id or '',
            conversation_id=conversation_id,
            total_turns=result['total_turns'],
            total_duration_ms=result['summary'].get('total_duration_ms'),
            turns=[Turn(**t) for t in result['turns']],
            summary=result['summary'],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
