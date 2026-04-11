"""
Session Cache for IVA Log Tracer

Provides in-memory caching for session logs to reduce Elasticsearch queries.
"""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional


@dataclass
class CacheEntry:
    """Single cache entry with TTL"""
    logs: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def hit(self):
        self.hit_count += 1


class SessionCache:
    """
    In-memory cache for session logs
    
    Features:
    - TTL-based expiration
    - Per-component caching within sessions
    - Thread-safe operations
    - Cache statistics
    """
    
    def __init__(self, default_ttl: int = 300, max_entries: int = 1000):
        """
        Initialize cache
        
        Args:
            default_ttl: Default time-to-live in seconds (5 minutes)
            max_entries: Maximum number of cache entries
        """
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }
    
    def _make_key(self, session_id: str, component: str) -> str:
        """Generate cache key"""
        return f"{session_id}:{component}"
    
    def get(
        self, 
        session_id: str, 
        component: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get logs from cache
        
        Args:
            session_id: Session ID
            component: Component name
            
        Returns:
            Cached logs or None if not found/expired
        """
        key = self._make_key(session_id, component)
        
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            entry.hit()
            self._stats["hits"] += 1
            return entry.logs
    
    def set(
        self,
        session_id: str,
        component: str,
        logs: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ):
        """
        Store logs in cache
        
        Args:
            session_id: Session ID
            component: Component name
            logs: Log entries to cache
            ttl: Optional custom TTL in seconds
        """
        key = self._make_key(session_id, component)
        effective_ttl = ttl if ttl is not None else self.default_ttl
        
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_entries and key not in self._cache:
                self._evict_oldest()
            
            self._cache[key] = CacheEntry(
                logs=logs,
                expires_at=time.time() + effective_ttl,
            )
    
    def invalidate(self, session_id: str, component: Optional[str] = None):
        """
        Invalidate cache entries
        
        Args:
            session_id: Session ID
            component: Optional component. If None, invalidates all components for session.
        """
        with self._lock:
            if component:
                key = self._make_key(session_id, component)
                if key in self._cache:
                    del self._cache[key]
            else:
                # Invalidate all components for this session
                keys_to_delete = [
                    k for k in self._cache 
                    if k.startswith(f"{session_id}:")
                ]
                for key in keys_to_delete:
                    del self._cache[key]
    
    def invalidate_all(self):
        """Clear entire cache"""
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0}
    
    def _evict_oldest(self):
        """Evict oldest entry (LRU-like)"""
        if not self._cache:
            return
        
        # Find entry with lowest hit count and oldest creation time
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: (self._cache[k].hit_count, -self._cache[k].created_at)
        )
        del self._cache[oldest_key]
        self._stats["evictions"] += 1
    
    def cleanup_expired(self):
        """Remove all expired entries"""
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if v.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            
            return {
                "entries": len(self._cache),
                "max_entries": self.max_entries,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "evictions": self._stats["evictions"],
                "hit_rate": round(hit_rate * 100, 2),
            }


# Global cache instance
session_cache = SessionCache()
