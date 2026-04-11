from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _find_dependency_root(relative_path: str) -> Path | None:
    for parent in PACKAGE_ROOT.parents:
        candidate = parent / relative_path
        if candidate.exists():
            return candidate
    return None


DEPENDENCY_ROOTS = [
    PACKAGE_ROOT,
    _find_dependency_root("tools/python/libs/jira"),
    _find_dependency_root("tools/python/libs/common"),
    _find_dependency_root("packages/python-common"),
]

for root in DEPENDENCY_ROOTS:
    if root is None:
        continue
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


@pytest.fixture(autouse=True)
def isolate_runtime_home(monkeypatch: pytest.MonkeyPatch):
    config_home = Path(tempfile.mkdtemp(prefix="jira-ticket-sync-config-"))
    cache_home = Path(tempfile.mkdtemp(prefix="jira-ticket-sync-cache-"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    for key in (
        "JIRA_TICKET_SYNC_HOME",
        "JIRA_TICKET_SYNC_WORKSPACE_ROOT",
        "JIRA_TICKET_SYNC_MANIFEST_ROOT",
        "JIRA_TICKET_SYNC_PROFILE_ROOT",
        "JIRA_TICKET_SYNC_TEMPLATE_ROOT",
        "JIRA_TICKET_SYNC_PROJECT_CONFIG_PATH",
        "JIRA_TICKET_SYNC_STATE_FILE",
        "JIRA_TICKET_SYNC_FIELD_CLASSIFICATION_ROOT",
        "JIRA_TICKET_SYNC_CACHE_DIR",
        "JIRA_TICKET_SYNC_OUTPUT_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
