#!/usr/bin/env python3
"""
Upload State Manager

Manages the mapping between local Markdown files and Confluence pages.
Supports incremental uploads by tracking content hashes.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class UploadState:
    """
    Manages Markdown file ↔ Confluence page mapping state.

    State file format (.upload_state.json):
    {
        "version": 1,
        "last_upload": "2026-01-08T10:00:00",
        "files": {
            "docs/guide.md": {
                "page_id": "12345678",
                "space_key": "IVA",
                "title": "User Guide",
                "content_hash": "abc123...",
                "last_uploaded": "2026-01-08T10:00:00",
                "remote_version": 15
            }
        }
    }
    """

    VERSION = 1

    def __init__(self, state_file: str = ".upload_state.json"):
        """
        Initialize the upload state manager.

        Args:
            state_file: Path to the state file
        """
        self.state_file = Path(state_file)
        self.state: Dict[str, Any] = {
            "version": self.VERSION,
            "last_upload": None,
            "files": {}
        }
        self._dirty = False
        self.load()

    def load(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)

            # Version check
            if loaded_state.get("version", 0) != self.VERSION:
                # Migration logic if needed
                loaded_state["version"] = self.VERSION
                self._dirty = True

            self.state = loaded_state

        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Warning: Could not load upload state file: {e}")

    def save(self) -> None:
        """Save state to file."""
        if not self._dirty:
            return

        self.state["last_upload"] = datetime.now().isoformat()

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)

            self._dirty = False

        except IOError as e:
            print(f"❌ Error saving upload state file: {e}")

    def get_page_id(self, md_path: str) -> Optional[str]:
        """Get the mapped page ID for a file path."""
        file_state = self.state.get("files", {}).get(md_path)
        if file_state:
            return file_state.get("page_id")
        return None

    def set_mapping(
        self,
        md_path: str,
        page_id: str,
        space_key: str,
        title: str,
        content_hash: str,
        remote_version: int,
    ) -> None:
        """Set or update file mapping."""
        if "files" not in self.state:
            self.state["files"] = {}

        self.state["files"][md_path] = {
            "page_id": page_id,
            "space_key": space_key,
            "title": title,
            "content_hash": content_hash,
            "last_uploaded": datetime.now().isoformat(),
            "remote_version": remote_version,
        }

        self._dirty = True

    def is_content_changed(self, md_path: str, current_hash: str) -> bool:
        """Check if file content has changed since last upload."""
        file_state = self.state.get("files", {}).get(md_path)
        if not file_state:
            return True  # New file
        return file_state.get("content_hash") != current_hash

    def get_file_state(self, md_path: str) -> Optional[Dict[str, Any]]:
        """Get the stored state for a specific file."""
        return self.state.get("files", {}).get(md_path)

    def remove_mapping(self, md_path: str) -> None:
        """Remove a file mapping."""
        files = self.state.get("files", {})
        if md_path in files:
            del files[md_path]
            self._dirty = True

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute MD5 hash of content."""
        return hashlib.md5(content.encode()).hexdigest()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the upload state."""
        files = self.state.get("files", {})
        return {
            "total_files": len(files),
            "last_upload": self.state.get("last_upload"),
        }

