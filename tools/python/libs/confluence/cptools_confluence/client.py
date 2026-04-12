#!/usr/bin/env python3
"""
Confluence Client Wrapper

Unified Confluence API client using atlassian-python-api library.
Provides a consistent interface for all extractors and tools.
"""

import os
from typing import Dict, Generator, List, Optional

from atlassian import Confluence


class ConfluenceClient:
    """
    Unified Confluence client wrapper.

    Wraps atlassian-python-api's Confluence class with additional convenience methods.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        use_bearer_token: bool = False,
    ):
        """
        Initialize Confluence client.

        Args:
            base_url: Confluence base URL (e.g., https://wiki.example.com)
            username: Confluence username/email
            api_token: Confluence API token or password
            use_bearer_token: If True, use Bearer token auth (for PAT)
        """
        self.base_url = base_url.rstrip("/")

        # Determine if this is Confluence Cloud
        is_cloud = ".atlassian.net" in base_url

        if use_bearer_token:
            # Personal Access Token (Server/Data Center)
            self.client = Confluence(
                url=self.base_url,
                token=api_token,
            )
        elif is_cloud:
            # Confluence Cloud uses API token with username
            self.client = Confluence(
                url=self.base_url,
                username=username,
                password=api_token,
                cloud=True,
            )
        else:
            # Confluence Server/Data Center with basic auth
            self.client = Confluence(
                url=self.base_url,
                username=username,
                password=api_token,
            )

    def test_connection(self) -> bool:
        """Test if the connection and authentication work."""
        try:
            spaces = self.client.get_all_spaces(limit=1)
            return bool(spaces)
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False

    def get_page_by_id(
        self,
        page_id: str,
        expand: str = "body.storage,version,space,ancestors,metadata.labels",
    ) -> Optional[Dict]:
        """Get a page by its ID."""
        try:
            return self.client.get_page_by_id(page_id, expand=expand)
        except Exception as e:
            print(f"❌ Error fetching page {page_id}: {e}")
            return None

    def get_all_pages_from_space(
        self,
        space_key: str,
        expand: str = "body.storage,version,ancestors,metadata.labels",
        limit: int = 100,
    ) -> List[Dict]:
        """
        Get all pages from a Confluence space.

        Args:
            space_key: The space key (e.g., 'IVA')
            expand: Properties to expand
            limit: Page size for pagination

        Returns:
            List of page objects
        """
        pages = []
        start = 0

        print(f"📥 Fetching pages from space: {space_key}")

        while True:
            try:
                batch = self.client.get_all_pages_from_space(
                    space_key,
                    start=start,
                    limit=limit,
                    expand=expand,
                    content_type="page",
                )

                if not batch:
                    break

                pages.extend(batch)
                print(f"  Fetched {len(pages)} pages so far...")

                if len(batch) < limit:
                    break

                start += limit

            except Exception as e:
                print(f"❌ Error fetching pages: {e}")
                break

        print(f"✅ Total pages fetched: {len(pages)}")
        return pages

    def get_all_pages_generator(
        self,
        space_key: str,
        expand: str = "body.storage,version,ancestors,metadata.labels",
    ) -> Generator[Dict, None, None]:
        """Get all pages as a generator for memory efficiency."""
        yield from self.client.get_all_pages_from_space_as_generator(
            space_key,
            expand=expand,
            content_type="page",
        )

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        parent_id: Optional[str] = None,
        minor_edit: bool = False,
    ) -> Dict:
        """Update an existing page.

        Avoid atlassian-python-api's legacy `status=current` update path, which
        fails against this Confluence deployment for current pages.
        """
        version = self.client.history(page_id)["lastUpdated"]["number"] + 1
        data = {
            "id": page_id,
            "type": "page",
            "title": title,
            "version": {
                "number": version,
                "minorEdit": minor_edit,
            },
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
            "metadata": {
                "properties": {
                    "content-appearance-draft": {"value": "fixed-width"},
                    "content-appearance-published": {"value": "fixed-width"},
                }
            },
        }
        if parent_id:
            data["ancestors"] = [{"type": "page", "id": parent_id}]

        return self.client.put(f"rest/api/content/{page_id}", data=data)

    def create_page(
        self,
        space: str,
        title: str,
        body: str,
        parent_id: Optional[str] = None,
    ) -> Dict:
        """Create a new page."""
        return self.client.create_page(
            space=space,
            title=title,
            body=body,
            parent_id=parent_id,
        )

    def get_attachments(
        self,
        page_id: str,
        filename: Optional[str] = None,
    ) -> List[Dict]:
        """Get attachments from a page."""
        try:
            result = self.client.get_attachments_from_content(
                page_id,
                filename=filename,
            )
            return result.get("results", []) if isinstance(result, dict) else result
        except Exception as e:
            print(f"⚠️ Error getting attachments: {e}")
            return []

    def download_attachment(
        self,
        page_id: str,
        filename: str,
        output_path: str,
    ) -> bool:
        """
        Download a specific attachment from a page.

        Args:
            page_id: The page ID
            filename: The attachment filename
            output_path: Local path to save the file

        Returns:
            True if successful, False otherwise
        """
        try:
            attachments = self.get_attachments(page_id, filename=filename)
            if not attachments:
                return False

            attachment = attachments[0]
            download_link = attachment["_links"]["download"]
            download_url = self.base_url + download_link

            # Use the underlying session from the client
            response = self.client._session.get(download_url, stream=True)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return True
        except Exception as e:
            print(f"⚠️ Failed to download {filename}: {e}")
            return False

    def download_all_attachments(
        self,
        page_id: str,
        output_dir: str,
    ) -> List[str]:
        """Download all attachments from a page."""
        os.makedirs(output_dir, exist_ok=True)

        downloaded = []
        attachments = self.get_attachments(page_id)

        for att in attachments:
            filename = att.get("title", att.get("id", "unknown"))
            output_path = os.path.join(output_dir, filename)

            if self.download_attachment(page_id, filename, output_path):
                downloaded.append(output_path)

        return downloaded

    def export_page_as_pdf(self, page_id: str) -> Optional[bytes]:
        """
        Export a page as PDF.

        Returns:
            PDF content as bytes, or None if failed
        """
        try:
            return self.client.export_page(page_id)
        except Exception as e:
            print(f"⚠️ Failed to export page {page_id} as PDF: {e}")
            return None

    def get_page_labels(self, page_id: str) -> List[str]:
        """Get labels for a page."""
        try:
            labels = self.client.get_page_labels(page_id)
            if isinstance(labels, dict):
                return [label["name"] for label in labels.get("results", [])]
            return [label["name"] for label in labels] if labels else []
        except Exception:
            return []

    def get_space_info(self, space_key: str) -> Optional[Dict]:
        """Get space information."""
        try:
            return self.client.get_space(space_key, expand="description.plain,homepage")
        except Exception as e:
            print(f"❌ Error fetching space {space_key}: {e}")
            return None

    def get_page_by_title(
        self,
        space_key: str,
        title: str,
        expand: str = "version",
    ) -> Optional[Dict]:
        """
        Get a page by its title within a space.

        Args:
            space_key: The space key
            title: The page title
            expand: Properties to expand

        Returns:
            Page object if found, None otherwise
        """
        try:
            return self.client.get_page_by_title(
                space=space_key,
                title=title,
                expand=expand,
            )
        except Exception:
            return None

    def upload_attachment(
        self,
        page_id: str,
        file_path: str,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Upload an attachment to a page.

        Args:
            page_id: Target page ID
            file_path: Local file path
            filename: Attachment name (optional, defaults to file name)
            content_type: MIME type (optional, auto-detected)

        Returns:
            Attachment info if successful, None otherwise
        """
        try:
            return self.client.attach_file(
                filename=file_path,
                name=filename,
                content_type=content_type,
                page_id=page_id,
            )
        except Exception as e:
            print(f"⚠️ Failed to upload attachment: {e}")
            return None

    def get_page_version(self, page_id: str) -> int:
        """
        Get the current version number of a page.

        Args:
            page_id: The page ID

        Returns:
            Version number, 0 if not found
        """
        page = self.get_page_by_id(page_id, expand="version")
        if page:
            return page.get("version", {}).get("number", 0)
        return 0

    def cql(
        self,
        query: str,
        limit: int = 25,
        start: int = 0,
    ) -> Dict:
        """
        Search using Confluence Query Language (CQL).

        Args:
            query: CQL query string
            limit: Maximum results to return
            start: Start index for pagination

        Returns:
            Search results dictionary
        """
        return self.client.cql(query, limit=limit, start=start)

    @property
    def session(self):
        """Access the underlying requests session."""
        return self.client._session
