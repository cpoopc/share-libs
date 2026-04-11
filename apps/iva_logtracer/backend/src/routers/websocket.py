"""
WebSocket Router for IVA Log Tracer

Provides WebSocket endpoints for real-time log streaming.
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.iva_logtracer.logtracer_extractors.iva.orchestrator import SessionTraceOrchestrator

from ..websocket import WSMessageHandlers, ws_manager
from .logtracer import get_client

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/session/{session_id}")
async def session_stream(
    websocket: WebSocket,
    session_id: str,
    auto_poll: bool = Query(default=False, description="Enable auto-polling for new logs"),
    poll_interval: int = Query(default=5, description="Poll interval in seconds (if auto_poll=True)"),
):
    """
    WebSocket endpoint for real-time session log streaming
    
    Args:
        session_id: The session ID to subscribe to
        auto_poll: Whether to automatically poll for new logs
        poll_interval: Interval between polls in seconds
    
    Message Types (Client -> Server):
        - subscribe: {"type": "subscribe", "components": ["ar", "agent"]}
        - unsubscribe: {"type": "unsubscribe", "components": ["ar"]}
        - time_sync: {"type": "time_sync", "timestamp": "...", "source_panel": 0}
        - ping: {"type": "ping"}
        - get_status: {"type": "get_status"}
    
    Message Types (Server -> Client):
        - connected: Initial connection confirmation
        - subscribed/unsubscribed: Subscription confirmations
        - logs: New log data
        - time_sync: Time sync broadcast from another client
        - pong: Response to ping
        - status: Connection status
        - error: Error message
    """
    conn_id = await ws_manager.connect(websocket, session_id)
    
    # Background polling task
    poll_task: Optional[asyncio.Task] = None
    
    async def poll_logs():
        """Background task to poll for new logs"""
        client = get_client()
        SessionTraceOrchestrator(client)
        
        while True:
            try:
                await asyncio.sleep(poll_interval)
                
                # Get subscribed components
                if conn_id not in ws_manager.connections:
                    break
                    
                components = ws_manager.connections[conn_id].subscribed_components
                if not components:
                    continue
                
                # Poll each component for new logs
                for component in components:
                    # This is a simplified polling - in production you'd want
                    # to track last timestamp and only fetch newer logs
                    pass  # TODO: Implement incremental log fetching
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                await ws_manager.send_to_connection(conn_id, {
                    "type": "error",
                    "error": f"Poll error: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                })
    
    try:
        # Start polling if enabled
        if auto_poll:
            poll_task = asyncio.create_task(poll_logs())
        
        # Main message loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                
                # Handle message
                response = await WSMessageHandlers.handle_message(
                    conn_id=conn_id,
                    session_id=session_id,
                    message=data,
                )
                
                # Send response if any
                if response:
                    await ws_manager.send_to_connection(conn_id, response)
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                await ws_manager.send_to_connection(conn_id, {
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })
                
    finally:
        # Cleanup
        if poll_task:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
        
        await ws_manager.disconnect(conn_id)


@router.get("/stats")
async def get_ws_stats():
    """Get WebSocket connection statistics"""
    return ws_manager.get_all_stats()
