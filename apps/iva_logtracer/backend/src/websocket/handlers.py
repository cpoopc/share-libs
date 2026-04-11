"""
WebSocket Message Handlers for IVA Log Tracer

Processes incoming WebSocket messages and dispatches to appropriate handlers.
"""

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import WebSocket

from .manager import ws_manager

# Message handler type
MessageHandler = Callable[[str, str, dict], Awaitable[None]]


class WSMessageHandlers:
    """
    WebSocket Message Handlers
    
    Handles different message types from clients:
    - subscribe: Subscribe to component logs
    - unsubscribe: Unsubscribe from component logs
    - time_sync: Broadcast time sync event
    - ping: Keep-alive ping
    """
    
    @staticmethod
    async def handle_message(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> Optional[dict]:
        """
        Route message to appropriate handler
        
        Args:
            conn_id: Connection ID
            session_id: Session ID
            message: The message to handle
            
        Returns:
            Response message or None
        """
        msg_type = message.get("type")
        
        handlers = {
            "subscribe": WSMessageHandlers.handle_subscribe,
            "unsubscribe": WSMessageHandlers.handle_unsubscribe,
            "time_sync": WSMessageHandlers.handle_time_sync,
            "ping": WSMessageHandlers.handle_ping,
            "get_status": WSMessageHandlers.handle_get_status,
        }
        
        handler = handlers.get(msg_type)
        if handler:
            return await handler(conn_id, session_id, message)
        else:
            return {
                "type": "error",
                "error": f"Unknown message type: {msg_type}",
                "timestamp": datetime.now().isoformat(),
            }
    
    @staticmethod
    async def handle_subscribe(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> dict:
        """
        Handle component subscription
        
        Message format:
        {
            "type": "subscribe",
            "components": ["assistant_runtime", "agent_service"]
        }
        """
        components = message.get("components", [])
        
        if not components:
            return {
                "type": "error",
                "error": "No components specified",
                "timestamp": datetime.now().isoformat(),
            }
        
        await ws_manager.subscribe(conn_id, components)
        
        return {
            "type": "subscribed",
            "components": components,
            "timestamp": datetime.now().isoformat(),
        }
    
    @staticmethod
    async def handle_unsubscribe(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> dict:
        """
        Handle component unsubscription
        
        Message format:
        {
            "type": "unsubscribe",
            "components": ["assistant_runtime"]
        }
        """
        components = message.get("components", [])
        
        if not components:
            return {
                "type": "error",
                "error": "No components specified",
                "timestamp": datetime.now().isoformat(),
            }
        
        await ws_manager.unsubscribe(conn_id, components)
        
        return {
            "type": "unsubscribed",
            "components": components,
            "timestamp": datetime.now().isoformat(),
        }
    
    @staticmethod
    async def handle_time_sync(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> Optional[dict]:
        """
        Handle time sync broadcast
        
        Message format:
        {
            "type": "time_sync",
            "timestamp": "2024-01-01T12:00:00.000Z",
            "source_panel": 0
        }
        """
        timestamp = message.get("timestamp")
        source_panel = message.get("source_panel", 0)
        
        if not timestamp:
            return {
                "type": "error",
                "error": "No timestamp specified",
                "timestamp": datetime.now().isoformat(),
            }
        
        # Broadcast to all connections in the room
        await ws_manager.broadcast_time_sync(
            session_id=session_id,
            timestamp=timestamp,
            source_panel=source_panel,
            source_conn_id=conn_id,
        )
        
        # No response needed, the broadcast is the response
        return None
    
    @staticmethod
    async def handle_ping(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> dict:
        """
        Handle ping message (keep-alive)
        
        Message format:
        {
            "type": "ping"
        }
        """
        return {
            "type": "pong",
            "timestamp": datetime.now().isoformat(),
        }
    
    @staticmethod
    async def handle_get_status(
        conn_id: str,
        session_id: str,
        message: dict
    ) -> dict:
        """
        Handle status request
        
        Message format:
        {
            "type": "get_status"
        }
        """
        room_stats = ws_manager.get_room_stats(session_id)
        
        return {
            "type": "status",
            "session_id": session_id,
            "connection_id": conn_id,
            "room": room_stats,
            "timestamp": datetime.now().isoformat(),
        }
