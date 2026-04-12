#!/usr/bin/env python3
"""
Enhanced Confluence Space Extractor with Image Support
Extracts all pages from a Confluence space including:
- Images and attachments
- Draw.io diagrams (exported as PNG)
- Optional PDF export
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

import html2text

# Import from cptools_confluence library
from cptools_confluence import ConfluenceClient


class ConfluenceExtractorWithImages:
    def __init__(self, base_url: str, username: str, api_token: str, use_bearer_token: bool = False):
        self.base_url = base_url.rstrip('/')
        self.username = username

        # Initialize Confluence client using atlassian-python-api
        self.client = ConfluenceClient(
            base_url=base_url,
            username=username,
            api_token=api_token,
            use_bearer_token=use_bearer_token,
        )

        # HTML to Markdown converter
        self.h2t = html2text.HTML2Text()
        self.h2t.body_width = 0  # Don't wrap lines
        self.h2t.ignore_links = False
        self.h2t.ignore_images = False
        self.h2t.ignore_emphasis = False

    def test_connection(self) -> bool:
        """Test if authentication works"""
        return self.client.test_connection()

    def get_space_key_from_url(self, url: str) -> Optional[str]:
        """Extract space key from Confluence URL"""
        match = re.search(r'/spaces/([A-Z0-9]+)/', url)
        if match:
            return match.group(1)
        return None

    def fetch_all_pages(self, space_key: str) -> List[Dict]:
        """Fetch all pages from a space"""
        try:
            pages = self.client.get_all_pages_from_space(
                space_key=space_key,
                expand='body.storage,version,ancestors,metadata.labels',
                limit=100
            )
            return pages
        except Exception as e:
            print(f"❌ Error fetching pages: {e}")
            return []
    
    def download_attachment(self, page_id: str, filename: str, output_dir: Path) -> Optional[str]:
        """Download an attachment from a page"""
        try:
            # Get attachment info using the client
            attachments = self.client.get_attachments(page_id, filename=filename)
            if not attachments:
                return None

            attachment = attachments[0]
            download_url = self.base_url + attachment['_links']['download']

            # Download the file using the client's session
            file_response = self.client.session.get(download_url, stream=True)
            if file_response.status_code == 200:
                # Create attachments directory
                attachments_dir = output_dir / 'attachments'
                attachments_dir.mkdir(parents=True, exist_ok=True)

                # Save file
                safe_filename = self._sanitize_filename(filename)
                file_path = attachments_dir / safe_filename

                with open(file_path, 'wb') as f:
                    for chunk in file_response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Return relative path for markdown
                return f"attachments/{safe_filename}"
        except Exception as e:
            print(f"   ⚠️  Failed to download {filename}: {e}")
        return None

    def export_drawio_diagram(self, page_id: str, diagram_name: str, output_dir: Path) -> Optional[str]:
        """Export a Draw.io diagram as PNG"""
        try:
            # Confluence Draw.io diagrams can be exported via a special endpoint
            # Try to find the PNG version first
            attachments = self.client.get_attachments(page_id, filename=f'{diagram_name}.png')
            if attachments:
                return self.download_attachment(page_id, f'{diagram_name}.png', output_dir)

            # Alternative: Try to find the .drawio file and export it
            attachments = self.client.get_attachments(page_id, filename=f'{diagram_name}.drawio')
            if attachments:
                # Download the .drawio file
                return self.download_attachment(page_id, f'{diagram_name}.drawio', output_dir)
        except Exception as e:
            print(f"   ⚠️  Failed to export diagram {diagram_name}: {e}")
        return None

    def process_html_content(self, html_content: str, page_id: str, output_dir: Path) -> str:
        """Process HTML content to download images and convert to Markdown"""
        # Find all image attachments
        attachment_pattern = r'<ri:attachment ri:filename="([^"]+)"'
        attachments = re.findall(attachment_pattern, html_content)

        # Download attachments and replace references
        for filename in set(attachments):
            local_path = self.download_attachment(page_id, filename, output_dir)
            if local_path:
                # Replace Confluence image syntax with Markdown
                html_content = re.sub(
                    r'<ac:image[^>]*>.*?<ri:attachment ri:filename="' + re.escape(filename) + r'".*?</ac:image>',
                    f'![{filename}]({local_path})',
                    html_content,
                    flags=re.DOTALL
                )

        # Find and export Draw.io diagrams
        drawio_pattern = r'<ac:structured-macro ac:name="drawio"[^>]*>.*?<ac:parameter ac:name="diagramName">([^<]+)</ac:parameter>.*?</ac:structured-macro>'
        diagrams = re.findall(drawio_pattern, html_content, re.DOTALL)

        for diagram_name in set(diagrams):
            local_path = self.export_drawio_diagram(page_id, diagram_name, output_dir)
            if local_path:
                # Replace Draw.io macro with Markdown image
                html_content = re.sub(
                    r'<ac:structured-macro ac:name="drawio"[^>]*>.*?<ac:parameter ac:name="diagramName">' + re.escape(diagram_name) + r'</ac:parameter>.*?</ac:structured-macro>',
                    f'\n\n![{diagram_name}]({local_path})\n\n',
                    html_content,
                    flags=re.DOTALL
                )

        # Convert HTML to Markdown
        markdown = self.h2t.handle(html_content)
        return markdown

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem usage"""
        # Replace unsafe characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext
        return filename

    def _get_breadcrumb(self, page: Dict) -> str:
        """Get page breadcrumb from ancestors"""
        ancestors = page.get('ancestors', [])
        breadcrumb_parts = [a['title'] for a in ancestors]
        breadcrumb_parts.append(page['title'])
        return ' > '.join(breadcrumb_parts)

    def _get_page_path(self, page: Dict, output_dir: Path) -> Path:
        """Generate file path for a page based on its hierarchy"""
        ancestors = page.get('ancestors', [])
        path_parts = [self._sanitize_filename(a['title']) for a in ancestors]

        # Create directory structure
        current_dir = output_dir
        for part in path_parts:
            current_dir = current_dir / part

        current_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = self._sanitize_filename(page['title']) + '.md'
        return current_dir / filename

    def save_page(self, page: Dict, output_dir: Path) -> bool:
        """Save a single page as Markdown with images"""
        try:
            title = page['title']
            page_id = page['id']

            # Get HTML content
            html_content = page.get('body', {}).get('storage', {}).get('value', '')
            if not html_content:
                print(f"⚠️  Skipping page '{title}' (no content)")
                return False

            # Get file path
            file_path = self._get_page_path(page, output_dir)

            # Process HTML and download images
            markdown_content = self.process_html_content(html_content, page_id, file_path.parent)

            # Get metadata
            version = page.get('version', {}).get('number', 'unknown')
            last_updated = page.get('version', {}).get('when', '')
            last_updated_by = page.get('version', {}).get('by', {}).get('displayName', 'Unknown')
            labels = [label['name'] for label in page.get('metadata', {}).get('labels', {}).get('results', [])]
            breadcrumb = self._get_breadcrumb(page)
            page_url = f"{self.base_url}/spaces/{page.get('_expandable', {}).get('space', '').split('/')[-1]}/pages/{page_id}"

            # Create frontmatter
            frontmatter = f"""---
title: {title}
confluence_id: {page_id}
confluence_url: {page_url}
version: {version}
last_updated: {last_updated}
last_updated_by: {last_updated_by}
tags: {json.dumps(labels)}
breadcrumb: {breadcrumb}
---

"""

            # Write file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter)
                f.write(markdown_content)

            return True

        except Exception as e:
            print(f"❌ Error saving page '{page.get('title', 'unknown')}': {e}")
            return False

    def export_space(self, space_key: str, output_dir: str):
        """Export entire space to Markdown with images"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        print(f"🚀 Starting extraction...")
        print(f"   Base URL: {self.base_url}")
        print(f"   Space Key: {space_key}")
        print(f"   Output: {output_dir}")
        print()

        # Test connection
        print("🔍 Testing connection...")
        if not self.test_connection():
            print("❌ Authentication failed!")
            return
        print("✅ Authentication successful!")
        print()

        # Fetch all pages
        pages = self.fetch_all_pages(space_key)
        if not pages:
            print("❌ No pages found")
            return

        # Save pages
        print(f"\n📝 Saving {len(pages)} pages to {output_dir}\n")
        saved_count = 0

        for i, page in enumerate(pages, 1):
            title = page['title']
            print(f"[{i}/{len(pages)}] Processing: {title}")

            if self.save_page(page, output_path):
                file_path = self._get_page_path(page, output_path)
                print(f"✅ Saved: {file_path}")
                saved_count += 1

            # Be nice to the server
            time.sleep(0.1)

        # Create index
        self._create_index(pages, output_path)

        print(f"\n🎉 Extraction complete! Saved {saved_count}/{len(pages)} pages")
        print(f"📁 Files saved to: {output_dir}")

    def _create_index(self, pages: List[Dict], output_dir: Path):
        """Create an index file listing all pages"""
        index_path = output_dir / 'INDEX.md'

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write("# Confluence Space Index\n\n")
            f.write(f"Total pages: {len(pages)}\n\n")

            # Group by top-level ancestor
            root_pages = [p for p in pages if not p.get('ancestors')]
            [p for p in pages if p.get('ancestors')]

            f.write("## Root Pages\n\n")
            for page in sorted(root_pages, key=lambda p: p['title']):
                f.write(f"- [{page['title']}]({self._get_relative_path(page, output_dir)})\n")

            f.write("\n## All Pages (Alphabetical)\n\n")
            for page in sorted(pages, key=lambda p: p['title']):
                breadcrumb = self._get_breadcrumb(page)
                f.write(f"- [{page['title']}]({self._get_relative_path(page, output_dir)}) - `{breadcrumb}`\n")

        print(f"✅ Index saved: {index_path}")

    def _get_relative_path(self, page: Dict, output_dir: Path) -> str:
        """Get relative path for index links"""
        file_path = self._get_page_path(page, output_dir)
        return str(file_path.relative_to(output_dir))

    def export_page_as_pdf(self, page_id: str, output_path: Path) -> bool:
        """Export a single page as PDF using Confluence's PDF export"""
        try:
            # Confluence PDF export endpoint
            pdf_url = f"{self.base_url}/spaces/flyingpdf/pdfpageexport.action?pageId={page_id}"

            response = self.session.get(pdf_url, stream=True)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"   ⚠️  Failed to export PDF: {e}")
        return False


def main():
    try:
        from .sync_config import SyncConfig
    except ImportError:
        from sync_config import SyncConfig

    parser = argparse.ArgumentParser(
        description='Extract Confluence space to Markdown with images and optional PDF export'
    )

    # Config file option
    parser.add_argument('--config', help='Path to YAML configuration file')

    # Legacy options
    parser.add_argument('--url', help='Confluence base URL or page URL')
    parser.add_argument('--space-key', help='Space key (if not provided, will extract from URL)')
    parser.add_argument('--username', help='Confluence username/email')
    parser.add_argument('--token', help='Confluence API token')
    parser.add_argument('--output', help='Output directory (not required for --test)')
    parser.add_argument('--bearer', action='store_true', help='Use Bearer token authentication')
    parser.add_argument('--export-pdf', action='store_true', help='Also export pages as PDF')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    parser.add_argument('--dry-run', action='store_true', help='Preview mode, no actual download')

    args = parser.parse_args()

    # Config file mode
    if args.config:
        config = SyncConfig.from_yaml(args.config)

        for space_config in config.spaces:
            print(f"\n📂 Processing space: {space_config.key}")
            print(f"   Output: {space_config.output_dir}")

            if args.dry_run:
                print("   [DRY-RUN] Would extract markdown with images")
                continue

            extractor = ConfluenceExtractorWithImages(
                base_url=config.confluence_url,
                username=config.auth.username,
                api_token=config.auth.token,
                use_bearer_token=config.auth.use_bearer
            )

            if args.test:
                print("🔍 Testing connection...")
                if extractor.test_connection():
                    print("✅ Connection successful!")
                    pages = extractor.fetch_all_pages(space_config.key)
                    print(f"✅ Found {len(pages)} pages")
                else:
                    print("❌ Connection failed!")
                return

            extractor.export_space(space_config.key, space_config.output_dir)
        return

    # Legacy mode
    if not args.url or not args.username or not args.token:
        parser.error("--url, --username, and --token are required when not using --config")

    # Extract base URL
    if '/spaces/' in args.url or '/pages/' in args.url:
        base_url = args.url.split('/spaces/')[0] if '/spaces/' in args.url else args.url.split('/wiki')[0] + '/wiki'
    else:
        base_url = args.url

    # Create extractor
    extractor = ConfluenceExtractorWithImages(
        base_url=base_url,
        username=args.username,
        api_token=args.token,
        use_bearer_token=args.bearer
    )

    # Test mode
    if args.test:
        print("🔍 Testing connection...")
        if extractor.test_connection():
            print("✅ Connection successful!")

            # Try to get space info
            if args.space_key:
                space_key = args.space_key
            else:
                space_key = extractor.get_space_key_from_url(args.url)

            if space_key:
                print(f"✅ Space key: {space_key}")
                pages = extractor.fetch_all_pages(space_key)
                print(f"✅ Found {len(pages)} pages")
        else:
            print("❌ Connection failed!")
        return

    # Check output directory for non-test mode
    if not args.output:
        print("❌ --output is required for extraction mode")
        return

    # Get space key
    if args.space_key:
        space_key = args.space_key
    else:
        space_key = extractor.get_space_key_from_url(args.url)
        if not space_key:
            print("❌ Could not extract space key from URL. Please provide --space-key")
            return

    # Export space
    print(f"   Auth Method: {'Bearer Token' if args.bearer else 'Basic Auth'}")
    print()

    extractor.export_space(space_key, args.output)

    # Optional PDF export
    if args.export_pdf:
        print("\n📄 Exporting PDFs...")
        pdf_dir = Path(args.output) / 'pdfs'
        pdf_dir.mkdir(exist_ok=True)

        pages = extractor.fetch_all_pages(space_key)
        for i, page in enumerate(pages, 1):
            title = extractor._sanitize_filename(page['title'])
            pdf_path = pdf_dir / f"{title}.pdf"
            print(f"[{i}/{len(pages)}] Exporting PDF: {title}")
            extractor.export_page_as_pdf(page['id'], pdf_path)
            time.sleep(0.5)  # Be nice to the server


if __name__ == '__main__':
    main()

