#!/usr/bin/env python3
"""
Jira API Client
Provides a simple interface to interact with Jira REST API.

Environment Variables:
    JIRA_URL            - Jira server URL (e.g., https://jira.example.com)
    JIRA_USERNAME       - Jira username (email)
    JIRA_TOKEN          - Jira API Token / Personal Access Token
    JIRA_USE_BEARER     - Use Bearer auth instead of Basic (default: false)
    JIRA_STORY_POINTS_FIELD - Custom field ID for story points (default: customfield_10016)

    You can also create a .env file in this package directory.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
from cptools_common import load_dotenv


class JiraAPIError(Exception):
    """
    Jira API error with detailed field-level error information.

    Attributes:
        status_code: HTTP status code
        errors: Field-level errors (e.g., {"description": "Description is required."})
        error_messages: General error messages
        response_body: Raw response body for debugging
    """
    def __init__(
        self,
        status_code: int,
        errors: Optional[Dict[str, str]] = None,
        error_messages: Optional[List[str]] = None,
        response_body: Optional[str] = None
    ):
        self.status_code = status_code
        self.errors = errors or {}
        self.error_messages = error_messages or []
        self.response_body = response_body

        # Build human-readable error message
        details = []
        for field_name, msg in self.errors.items():
            details.append(f"  • {field_name}: {msg}")
        for msg in self.error_messages:
            details.append(f"  • {msg}")

        if details:
            message = f"Jira API Error ({status_code}):\n" + "\n".join(details)
        else:
            message = f"Jira API Error ({status_code}): {response_body or 'Unknown error'}"

        super().__init__(message)

# Auto-load .env from this package's directory (low priority, won't override existing env vars)
_PACKAGE_DIR = Path(__file__).parent.parent
load_dotenv(_PACKAGE_DIR / '.env')


@dataclass
class JiraConfig:
    """Jira connection configuration."""
    url: str
    username: str
    token: str
    use_bearer: bool = False
    story_points_field: str = "customfield_10016"

    @classmethod
    def from_env(cls, env_path: Optional[Union[str, Path]] = None) -> "JiraConfig":
        """
        Create config from environment variables.

        Args:
            env_path: Optional path to .env file. If provided, will load this file
                      additionally (higher priority than package's .env).
        """
        # Load additional .env file if specified
        if env_path:
            load_dotenv(env_path)

        url = os.getenv("JIRA_URL", "").rstrip("/")
        username = os.getenv("JIRA_USERNAME", "")
        token = os.getenv("JIRA_TOKEN", "")
        use_bearer = os.getenv("JIRA_USE_BEARER", "").lower() in ("true", "1", "yes")
        story_points_field = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10016")

        if not all([url, token]):
            raise ValueError(
                "Missing required environment variables: JIRA_URL, JIRA_TOKEN"
            )

        # Bearer auth doesn't need username
        if not use_bearer and not username:
            raise ValueError(
                "Missing JIRA_USERNAME (or set JIRA_USE_BEARER=true for Bearer auth)"
            )

        return cls(
            url=url,
            username=username,
            token=token,
            use_bearer=use_bearer,
            story_points_field=story_points_field
        )


class JiraClient:
    """Jira REST API client."""
    
    def __init__(self, config: JiraConfig):
        """Initialize Jira client with configuration."""
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.session = requests.Session()

        # Support different authentication methods
        if config.use_bearer:
            # Bearer token authentication (for Jira instances with Basic Auth disabled)
            self.session.headers.update({
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            })
        else:
            # Basic authentication (email + API token for Jira Cloud)
            self.session.auth = (config.username, config.token)
            self.session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json"
            })
    
    @classmethod
    def from_env(cls) -> "JiraClient":
        """Create client from environment variables."""
        return cls(JiraConfig.from_env())

    def _raise_for_status(self, response: requests.Response) -> None:
        """
        Check response status and raise JiraAPIError with detailed info if failed.

        This method parses Jira's error response format which typically looks like:
        {
            "errorMessages": ["Some general error"],
            "errors": {"fieldName": "Field-specific error message"}
        }
        """
        if response.ok:
            return

        # Try to parse Jira's error response
        errors = {}
        error_messages = []
        response_body = response.text

        try:
            data = response.json()
            errors = data.get("errors", {})
            error_messages = data.get("errorMessages", [])
        except (ValueError, KeyError):
            # Response is not JSON or doesn't have expected structure
            pass

        raise JiraAPIError(
            status_code=response.status_code,
            errors=errors,
            error_messages=error_messages,
            response_body=response_body
        )

    def test_connection(self) -> bool:
        """Test if the connection and authentication work."""
        try:
            response = self.session.get(f"{self.base_url}/rest/api/2/myself")
            if response.status_code == 200:
                user = response.json()
                print(f"✅ Connected as: {user.get('displayName', user.get('name'))}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def get_myself(self) -> Dict[str, Any]:
        """Get current user info."""
        response = self.session.get(f"{self.base_url}/rest/api/2/myself")
        response.raise_for_status()
        return response.json()
    
    def search_issues(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        max_results: int = 50,
        start_at: int = 0,
        expand: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Search issues using JQL.
        
        Args:
            jql: JQL query string
            fields: List of fields to return
            max_results: Maximum results per page
            start_at: Starting index for pagination
            expand: Fields to expand (e.g., ['changelog', 'renderedFields'])
        """
        url = f"{self.base_url}/rest/api/2/search"
        
        params = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand)
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def search_all_issues(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        expand: Optional[List[str]] = None,
        page_size: int = 50,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """Search all issues matching JQL (handles pagination)."""
        all_issues = []
        start_at = 0

        while True:
            result = self.search_issues(
                jql=jql,
                fields=fields,
                max_results=page_size,
                start_at=start_at,
                expand=expand
            )

            issues = result.get("issues", [])
            all_issues.extend(issues)

            total = result.get("total", 0)
            if verbose:
                print(f"  Fetched {len(all_issues)}/{total} issues...")

            if len(all_issues) >= total:
                break

            start_at += page_size

        return all_issues

    def get_issue(
        self,
        issue_key: str,
        fields: Optional[List[str]] = None,
        expand: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get a single issue by key."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}"

        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand)

        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_issue_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get all comments for an issue."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get("comments", [])

    def get_issue_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get available transitions for an issue."""
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get("transitions", [])

    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all accessible projects."""
        url = f"{self.base_url}/rest/api/2/project"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_boards(self, project_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all boards, optionally filtered by project."""
        url = f"{self.base_url}/rest/agile/1.0/board"
        params = {}
        if project_key:
            params["projectKeyOrId"] = project_key

        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json().get("values", [])

    def get_sprints(
        self,
        board_id: int,
        state: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get sprints for a board.

        Args:
            board_id: The board ID
            state: Filter by state (future, active, closed)
        """
        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint"
        params = {}
        if state:
            params["state"] = state

        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json().get("values", [])

    def add_issues_to_sprint(
        self,
        sprint_id: int,
        issue_keys: List[str],
    ) -> bool:
        """Add one or more issues to a sprint using the Agile API."""
        if not issue_keys:
            return True

        url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue"
        response = self.session.post(url, json={"issues": issue_keys})
        self._raise_for_status(response)
        return True

    def get_sprint(self, sprint_id: int) -> Dict[str, Any]:
        """Get sprint details."""
        url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_sprint_issues(
        self,
        sprint_id: int,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get all issues in a sprint."""
        url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue"

        all_issues = []
        start_at = 0
        max_results = 50

        while True:
            params = {"startAt": start_at, "maxResults": max_results}
            if fields:
                params["fields"] = ",".join(fields)

            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            all_issues.extend(issues)

            if len(all_issues) >= data.get("total", 0):
                break
            start_at += max_results

        return all_issues

    # ==================== Write Operations ====================
    
    def get_create_meta(
        self,
        project_key: str,
        issue_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get metadata needed to create an issue.
        
        Args:
            project_key: The project key (e.g., "PROJ")
            issue_type: Optional issue type name to filter (e.g., "Bug", "Task")
        
        Returns:
            Dictionary containing project info and available fields
        """
        url = f"{self.base_url}/rest/api/2/issue/createmeta"
        params = {
            "projectKeys": project_key,
            "expand": "projects.issuetypes.fields"
        }
        if issue_type:
            params["issuetypeNames"] = issue_type
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
        labels: Optional[List[str]] = None,
        components: Optional[List[str]] = None,
        parent_key: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new issue.
        
        Args:
            project_key: The project key (e.g., "PROJ")
            summary: Issue summary/title
            issue_type: Issue type (e.g., "Bug", "Task", "Story", "Sub-task")
            description: Issue description (optional)
            assignee: Assignee account ID or username (optional)
            priority: Priority name (e.g., "High", "Medium", "Low") (optional)
            labels: List of labels to apply (optional)
            components: List of component names (optional)
            parent_key: Parent issue key for sub-tasks (optional)
            custom_fields: Dictionary of custom field IDs to values (optional)
        
        Returns:
            Dictionary with created issue info (id, key, self)
        """
        url = f"{self.base_url}/rest/api/2/issue"
        
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type}
        }
        
        if description:
            fields["description"] = description
        if assignee:
            # Try accountId first (Jira Cloud), fall back to name (Jira Server)
            fields["assignee"] = {"accountId": assignee} if "@" not in assignee else {"name": assignee}
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = labels
        if components:
            fields["components"] = [{"name": c} for c in components]
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if custom_fields:
            fields.update(custom_fields)
        
        payload = {"fields": fields}

        response = self.session.post(url, json=payload)
        self._raise_for_status(response)
        return response.json()

    def update_issue(
        self,
        issue_key: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
        labels: Optional[List[str]] = None,
        custom_fields: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing issue.
        
        Args:
            issue_key: The issue key (e.g., "PROJ-123")
            summary: New summary (optional)
            description: New description (optional)
            assignee: New assignee (optional)
            priority: New priority (optional)
            labels: New labels - replaces existing labels (optional)
            custom_fields: Dictionary of custom field IDs to values (optional)
        
        Returns:
            True if update succeeded
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}"
        
        fields: Dict[str, Any] = {}
        
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = description
        if assignee is not None:
            fields["assignee"] = {"accountId": assignee} if "@" not in assignee else {"name": assignee}
        if priority is not None:
            fields["priority"] = {"name": priority}
        if labels is not None:
            fields["labels"] = labels
        if custom_fields:
            fields.update(custom_fields)
        
        if not fields:
            return True  # Nothing to update
        
        payload = {"fields": fields}

        response = self.session.put(url, json=payload)
        self._raise_for_status(response)
        return True

    def add_comment(self, issue_key: str, body: str) -> Dict[str, Any]:
        """
        Add a comment to an issue.
        
        Args:
            issue_key: The issue key (e.g., "PROJ-123")
            body: Comment text
        
        Returns:
            Dictionary with created comment info
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        payload = {"body": body}
        
        response = self.session.post(url, json=payload)
        self._raise_for_status(response)
        return response.json()

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Transition an issue to a new status.
        
        Args:
            issue_key: The issue key (e.g., "PROJ-123")
            transition_id: The transition ID (use get_issue_transitions to find available ones)
            comment: Optional comment to add during transition
            fields: Optional fields to update during transition
        
        Returns:
            True if transition succeeded
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/transitions"
        
        payload: Dict[str, Any] = {
            "transition": {"id": transition_id}
        }
        
        if comment:
            payload["update"] = {
                "comment": [{"add": {"body": comment}}]
            }
        if fields:
            payload["fields"] = fields

        response = self.session.post(url, json=payload)
        self._raise_for_status(response)
        return True

    def create_issue_link(
        self,
        from_issue: str,
        to_issue: str,
        link_type: str = "Relates"
    ) -> bool:
        """
        Create a link between two issues.

        Args:
            from_issue: The outward issue key (e.g., "PROJ-123")
            to_issue: The inward issue key (e.g., "PROJ-456")
            link_type: The link type name (e.g., "Blocks", "Relates", "Duplicates")

        Returns:
            True if link was created successfully
        """
        url = f"{self.base_url}/rest/api/2/issueLink"

        payload = {
            "type": {"name": link_type},
            "outwardIssue": {"key": from_issue},
            "inwardIssue": {"key": to_issue}
        }

        response = self.session.post(url, json=payload)
        self._raise_for_status(response)
        return True

    def get_link_types(self) -> List[Dict[str, Any]]:
        """
        Get all available issue link types.

        Returns:
            List of link type dictionaries with id, name, inward, outward fields
        """
        url = f"{self.base_url}/rest/api/2/issueLinkType"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get("issueLinkTypes", [])
