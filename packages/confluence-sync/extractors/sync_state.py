#!/usr/bin/env python3
"""
Sync State Manager
Manages the synchronization state to support incremental updates.
Tracks page IDs, last modified times, and file paths.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class PageState:
    """State information for a single page."""
    page_id: str
    last_modified: str
    file_path: str
    title: str
    sync_time: str = field(default_factory=lambda: datetime.now().isoformat())


class SyncStateManager:
    """
    Manages synchronization state for incremental updates.
    
    State file structure:
    {
        "version": 1,
        "last_sync": "2024-01-01T00:00:00",
        "spaces": {
            "SPACE_KEY": {
                "pages": {
                    "page_id": {
                        "last_modified": "2024-01-01T00:00:00",
                        "file_path": "path/to/file.md",
                        "title": "Page Title",
                        "sync_time": "2024-01-01T00:00:00"
                    }
                }
            }
        }
    }
    """

    VERSION = 1

    def __init__(self, state_file: str, space_key: str):
        """
        Initialize the sync state manager.
        
        Args:
            state_file: Path to the state file
            space_key: The Confluence space key
        """
        self.state_file = Path(state_file)
        self.space_key = space_key
        self.state: Dict[str, Any] = {
            "version": self.VERSION,
            "last_sync": None,
            "spaces": {}
        }
        self._dirty = False

    def load(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
                
            # Version check and migration if needed
            if loaded_state.get("version", 0) < self.VERSION:
                self._migrate_state(loaded_state)
            else:
                self.state = loaded_state
                
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️  Warning: Could not load state file: {e}")
            # Keep default empty state

    def save(self) -> None:
        """Save state to file."""
        if not self._dirty:
            return

        self.state["last_sync"] = datetime.now().isoformat()
        
        try:
            # Ensure parent directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
                
            self._dirty = False
            
        except IOError as e:
            print(f"❌ Error saving state file: {e}")

    def _migrate_state(self, old_state: Dict[str, Any]) -> None:
        """Migrate state from older versions."""
        # For now, just use defaults if version mismatch
        self.state = {
            "version": self.VERSION,
            "last_sync": old_state.get("last_sync"),
            "spaces": old_state.get("spaces", {})
        }
        self._dirty = True

    def _get_space_state(self) -> Dict[str, Any]:
        """Get or create state for current space."""
        if self.space_key not in self.state["spaces"]:
            self.state["spaces"][self.space_key] = {"pages": {}}
        return self.state["spaces"][self.space_key]

    def is_updated(self, page_id: str, last_modified: str) -> bool:
        """
        Check if a page has been updated since last sync.
        
        Args:
            page_id: The Confluence page ID
            last_modified: The page's last modified timestamp
            
        Returns:
            True if the page needs to be synced (new or updated)
        """
        space_state = self._get_space_state()
        pages = space_state.get("pages", {})
        
        if page_id not in pages:
            return True  # New page
            
        stored_modified = pages[page_id].get("last_modified")
        if not stored_modified:
            return True
            
        # Compare timestamps
        try:
            stored_dt = self._parse_timestamp(stored_modified)
            current_dt = self._parse_timestamp(last_modified)
            return current_dt > stored_dt
        except ValueError:
            # If parsing fails, assume updated
            return True

    def _parse_timestamp(self, timestamp: str) -> datetime:
        """Parse various timestamp formats from Confluence."""
        # Confluence uses ISO 8601 format
        # Examples: "2024-01-15T10:30:00.000Z", "2024-01-15T10:30:00+08:00"
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
                
        # Fallback: try fromisoformat (Python 3.7+)
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

    def update(self, page_id: str, last_modified: str, file_path: str, title: str) -> None:
        """
        Update the state for a synced page.
        
        Args:
            page_id: The Confluence page ID
            last_modified: The page's last modified timestamp
            file_path: The local file path where the page was saved
            title: The page title
        """
        space_state = self._get_space_state()
        
        if "pages" not in space_state:
            space_state["pages"] = {}
            
        space_state["pages"][page_id] = {
            "last_modified": last_modified,
            "file_path": file_path,
            "title": title,
            "sync_time": datetime.now().isoformat()
        }
        
        self._dirty = True

    def get_page_state(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Get the stored state for a specific page."""
        space_state = self._get_space_state()
        return space_state.get("pages", {}).get(page_id)

    def get_all_synced_pages(self) -> Dict[str, Dict[str, Any]]:
        """Get all synced page states for the current space."""
        space_state = self._get_space_state()
        return space_state.get("pages", {})

    def remove_page(self, page_id: str) -> None:
        """Remove a page from the state (e.g., if deleted from Confluence)."""
        space_state = self._get_space_state()
        pages = space_state.get("pages", {})
        
        if page_id in pages:
            del pages[page_id]
            self._dirty = True

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the sync state."""
        space_state = self._get_space_state()
        pages = space_state.get("pages", {})
        
        return {
            "total_pages": len(pages),
            "last_sync": self.state.get("last_sync"),
            "space_key": self.space_key
        }
