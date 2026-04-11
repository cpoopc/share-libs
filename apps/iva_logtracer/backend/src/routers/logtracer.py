"""
IVA Logtracer API Router
"""
from typing import List, Optional

import pydantic
from fastapi import APIRouter, HTTPException, Query

from apps.iva_logtracer.logtracer_extractors.iva.orchestrator import SessionTraceOrchestrator
from apps.iva_logtracer.logtracer_extractors.iva.trace_context import TraceContext
from apps.iva_logtracer.logtracer_extractors.kibana_client import KibanaClient
from apps.iva_logtracer.logtracer_extractors.log_searcher import LogSearcher

router = APIRouter(prefix="/logtracer", tags=["logtracer"])

# Global instances
_client: Optional[KibanaClient] = None

def get_client() -> KibanaClient:
    global _client
    if _client is None:
        _client = KibanaClient.from_env()
    return _client

@router.get("/components")
async def list_components():
    """List available components."""
    return [
        { "id": "assistant_runtime", "name": "assistant_runtime", "displayName": "Assistant Runtime" },
        { "id": "agent_service", "name": "agent_service", "displayName": "Agent Service" },
        { "id": "nca", "name": "nca", "displayName": "NCA" },
        { "id": "aig", "name": "aig", "displayName": "AIG" },
        { "id": "gmg", "name": "gmg", "displayName": "GMG" },
        { "id": "cprc_srs", "name": "cprc_srs", "displayName": "CPRC SRS" },
        { "id": "cprc_sgs", "name": "cprc_sgs", "displayName": "CPRC SGS" },
    ]

@router.get("/logs")
async def get_logs(
    component: str,
    sessionId: Optional[str] = None,
    conversationId: Optional[str] = None,
    timeRange: str = "1h",
    limit: int = 500
):
    """Fetch logs for a specific component."""
    client = get_client()
    searcher = LogSearcher(client)
    
    # Map component to index
    component_indices = {
        "assistant_runtime": "*:*-logs-air_assistant_runtime-*",
        "agent_service": "*:*-logs-air_agent_service-*",
        "nca": "*:*-logs-nca-*",
        "aig": "*:*-logs-aig-*",
        "gmg": "*:*-logs-gmg-*",
        "cprc_srs": "*:*-ai-cprc*",
        "cprc_sgs": "*:*-ai-cprc*",
    }
    
    index = component_indices.get(component)
    if not index:
        raise HTTPException(status_code=400, detail=f"Unknown component: {component}")
        
    query_parts = []
    if sessionId:
        query_parts.append(f"sessionId:\"{sessionId}\"")
    if conversationId:
        query_parts.append(f"conversationId:\"{conversationId}\"")
        
    query = " AND ".join(query_parts) if query_parts else "*"
    
    try:
        result = searcher.search(
            query=query,
            index=index,
            last=timeRange,
            size=limit
        )
        
        hits = result.get("hits", {}).get("hits", [])
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        
        logs = []
        for hit in hits:
            src = hit.get("_source", {})
            logs.append({
                "timestamp": src.get("@timestamp"),
                "type": "err" if src.get("level") == "ERROR" else "out",
                "message": src.get("message"),
                "source": component,
                "level": src.get("level"),
                "logger": src.get("logger")
            })
            
        return { "logs": logs, "total": total }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Trace a session across all components."""
    client = get_client()
    orchestrator = SessionTraceOrchestrator(client)
    
    try:
        ctx = orchestrator.trace_by_session(session_id)
        return ctx.to_result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
