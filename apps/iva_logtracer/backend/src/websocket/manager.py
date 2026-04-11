"""
WebSocket Connection Manager for IVA Log Tracer

Manages WebSocket connections organized by session rooms.
Supports real-time log streaming and synchronization.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection"""
    websocket: WebSocket
    session_id: str
    subscribed_components: Set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class LogWSManager:
    """
    WebSocket Connection Manager
    
    Manages connections organized by session rooms.
    Supports:
    - Room-based broadcasting (per session_id)
    - Component-level subscriptions
    - Time sync broadcasting
    """
    
    def __init__(self):
        # session_id -> set of connection IDs
        self.rooms: Dict[str, Set[str]] = {}
        # connection_id -> ConnectionInfo
        self.connections: Dict[str, ConnectionInfo] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        # Connection ID counter
        self._counter = 0
    
    def _generate_connection_id(self) -> str:
        """Generate unique connection ID"""
        self._counter += 1
        return f"conn_{self._counter}_{datetime.now().timestamp()}"
    
    async def connect(self, websocket: WebSocket, session_id: str) -> str:
        """
        Accept and register a new WebSocket connection
        
        Args:
            websocket: The WebSocket connection
            session_id: Session ID to join
            
        Returns:
            Connection ID
        """
        await websocket.accept()
        
        async with self._lock:
            conn_id = self._generate_connection_id()
            
            # Create connection info
            self.connections[conn_id] = ConnectionInfo(
                websocket=websocket,
                session_id=session_id,
            )
            
            # Add to session room
            if session_id not in self.rooms:
                self.rooms[session_id] = set()
            self.rooms[session_id].add(conn_id)
        
        # Send welcome message
        await self.send_to_connection(conn_id, {
            "type": "connected",
            "connection_id": conn_id,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        })
        
        return conn_id
    
    async def disconnect(self, conn_id: str):
        """
        Remove a WebSocket connection
        
        Args:
            conn_id: Connection ID to remove
        """
        async with self._lock:
            if conn_id not in self.connections:
                return
            
            conn_info = self.connections[conn_id]
            session_id = conn_info.session_id
            
            # Remove from room
            if session_id in self.rooms:
                self.rooms[session_id].discard(conn_id)
                if not self.rooms[session_id]:
                    del self.rooms[session_id]
            
            # Remove connection
            del self.connections[conn_id]
    
    async def subscribe(self, conn_id: str, components: List[str]):
        """
        Subscribe a connection to specific components
        
        Args:
            conn_id: Connection ID
            components: List of component names to subscribe to
        """
        async with self._lock:
            if conn_id in self.connections:
                self.connections[conn_id].subscribed_components.update(components)
                self.connections[conn_id].last_activity = datetime.now()
    
    async def unsubscribe(self, conn_id: str, components: List[str]):
        """
        Unsubscribe a connection from specific components
        
        Args:
            conn_id: Connection ID
            components: List of component names to unsubscribe from
        """
        async with self._lock:
            if conn_id in self.connections:
                for comp in components:
                    self.connections[conn_id].subscribed_components.discard(comp)
    
    async def send_to_connection(self, conn_id: str, message: dict) -> bool:
        """
        Send message to a specific connection
        
        Args:
            conn_id: Connection ID
            message: Message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if conn_id not in self.connections:
            return False
        
        try:
            await self.connections[conn_id].websocket.send_json(message)
            return True
        except Exception:
            # Connection might be closed
            await self.disconnect(conn_id)
            return False
    
    async def broadcast_to_room(
        self, 
        session_id: str, 
        message: dict,
        component: Optional[str] = None
    ):
        """
        Broadcast message to all connections in a session room
        
        Args:
            session_id: Session ID (room)
            message: Message to broadcast
            component: If specified, only send to connections subscribed to this component
        """
        if session_id not in self.rooms:
            return
        
        # Get connections in room
        conn_ids = list(self.rooms[session_id])
        
        for conn_id in conn_ids:
            if conn_id not in self.connections:
                continue
            
            conn_info = self.connections[conn_id]
            
            # Check component subscription if specified
            if component:
                if not conn_info.subscribed_components or component in conn_info.subscribed_components:
                    await self.send_to_connection(conn_id, message)
            else:
                await self.send_to_connection(conn_id, message)
    
    async def broadcast_logs(
        self,
        session_id: str,
        component: str,
        logs: List[dict],
        is_incremental: bool = True
    ):
        """
        Broadcast log updates to a session room
        
        Args:
            session_id: Session ID
            component: Component name
            logs: Log entries
            is_incremental: Whether this is an incremental update
        """
        message = {
            "type": "logs",
            "component": component,
            "logs": logs,
            "is_incremental": is_incremental,
            "timestamp": datetime.now().isoformat(),
        }
        await self.broadcast_to_room(session_id, message, component=component)
    
    async def broadcast_time_sync(
        self,
        session_id: str,
        timestamp: str,
        source_panel: int,
        source_conn_id: str
    ):
        """
        Broadcast time sync event to a session room
        
        Args:
            session_id: Session ID
            timestamp: The timestamp to sync to
            source_panel: Panel index that triggered the sync
            source_conn_id: Connection ID that triggered the sync
        """
        message = {
            "type": "time_sync",
            "timestamp": timestamp,
            "source_panel": source_panel,
            "source_conn_id": source_conn_id,
        }
        await self.broadcast_to_room(session_id, message)
    
    def get_room_stats(self, session_id: str) -> dict:
        """Get statistics for a session room"""
        if session_id not in self.rooms:
            return {"connections": 0, "components": []}
        
        conn_ids = self.rooms[session_id]
        all_components: Set[str] = set()
        
        for conn_id in conn_ids:
            if conn_id in self.connections:
                all_components.update(self.connections[conn_id].subscribed_components)
        
        return {
            "connections": len(conn_ids),
            "components": list(all_components),
        }
    
    def get_all_stats(self) -> dict:
        """Get overall statistics"""
        return {
            "total_connections": len(self.connections),
            "total_rooms": len(self.rooms),
            "rooms": {
                sid: self.get_room_stats(sid) 
                for sid in self.rooms
            }
        }


# Global manager instance
ws_manager = LogWSManager()
