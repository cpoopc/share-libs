#!/usr/bin/env python3
"""
Image Handler for Confluence Uploads

Handles uploading local images as Confluence page attachments
and updating references in the converted content.
"""

import mimetypes
import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    from ..extractors.confluence_client import ConfluenceClient
except ImportError:
    from extractors.confluence_client import ConfluenceClient


class ImageHandler:
    """
    Handles image uploads to Confluence pages.

    Uploads local images as attachments and updates CSF content
    to reference the uploaded attachments.
    """

    # Supported image extensions
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp', '.webp'}

    def __init__(self, client: ConfluenceClient):
        """
        Initialize the image handler.

        Args:
            client: Confluence API client
        """
        self.client = client

    def upload_images(
        self,
        page_id: str,
        images: List[Path],
        base_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        """
        Upload images to a Confluence page as attachments.

        Args:
            page_id: Target page ID
            images: List of image paths
            base_path: Base path for resolving relative paths

        Returns:
            Dict mapping original paths to attachment filenames
        """
        image_map: Dict[str, str] = {}

        for img_path in images:
            # Resolve path if base_path provided
            if base_path and not img_path.is_absolute():
                full_path = base_path / img_path
            else:
                full_path = img_path

            if not full_path.exists():
                print(f"⚠️ Image not found: {full_path}")
                continue

            if full_path.suffix.lower() not in self.IMAGE_EXTENSIONS:
                print(f"⚠️ Unsupported image format: {full_path.suffix}")
                continue

            # Upload the attachment
            filename = full_path.name
            content_type = mimetypes.guess_type(str(full_path))[0] or 'image/png'

            result = self.client.upload_attachment(
                page_id=page_id,
                file_path=str(full_path),
                filename=filename,
                content_type=content_type,
            )

            if result:
                image_map[str(img_path)] = filename
                print(f"  📷 Uploaded: {filename}")
            else:
                print(f"  ❌ Failed to upload: {filename}")

        return image_map

    def update_image_references(
        self,
        csf_content: str,
        image_map: Dict[str, str],
    ) -> str:
        """
        Update image references in CSF content.

        Replaces local image paths with Confluence attachment references.

        Args:
            csf_content: Confluence Storage Format content
            image_map: Mapping from original paths to attachment filenames

        Returns:
            Updated CSF content with correct attachment references
        """
        # The MDConverter already creates ac:image tags with ri:attachment
        # This method handles any edge cases or cleanup

        for original_path, filename in image_map.items():
            # Update any remaining src attributes pointing to local files
            original_filename = Path(original_path).name

            # Pattern to find img tags with this file
            pattern = rf'<img\s+[^>]*src=["\'](?:[^"\']*[/\\])?{re.escape(original_filename)}["\'][^>]*>'

            def replace_img(match):
                # Create Confluence image macro
                return f'''<ac:image>
<ri:attachment ri:filename="{filename}"/>
</ac:image>'''

            csf_content = re.sub(pattern, replace_img, csf_content, flags=re.IGNORECASE)

        return csf_content

    def find_images_in_markdown(
        self,
        markdown_content: str,
        base_path: Path,
    ) -> List[Path]:
        """
        Find all local image references in Markdown content.

        Args:
            markdown_content: Markdown content
            base_path: Base path for resolving relative paths

        Returns:
            List of paths to local images
        """
        images: List[Path] = []

        # Match markdown image syntax: ![alt](path)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        for match in re.finditer(pattern, markdown_content):
            img_path = match.group(2)

            # Skip URLs
            if img_path.startswith(('http://', 'https://', '//')):
                continue

            # Remove any query parameters or fragments
            img_path = img_path.split('?')[0].split('#')[0]

            full_path = base_path / img_path
            if full_path.exists():
                images.append(full_path)

        return images

