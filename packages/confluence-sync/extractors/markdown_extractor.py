#!/usr/bin/env python3
"""
Confluence Space Extractor
Extract all documents from a Confluence space and save them as markdown files.

Features:
- Configurable exclusion rules (by title, labels, ancestors)
- Multi-space sync support via config file
- Incremental updates based on page modification time
- Concurrent downloads for better performance
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

import html2text
from bs4 import BeautifulSoup

# Import from cptools_confluence library
from cptools_confluence import ConfluenceClient, ExcludeConfig, SpaceConfig, SyncConfig

# Import local modules
try:
    from .sync_state import SyncStateManager
except ImportError:
    from sync_state import SyncStateManager


class ConfluenceExtractor:
    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        use_bearer_token: bool = False,
        exclude_config: Optional[ExcludeConfig] = None,
        max_workers: int = 4,
        download_images: bool = True
    ):
        """
        Initialize Confluence extractor

        Args:
            base_url: Confluence base URL (e.g., https://wiki.ringcentral.com)
            username: Your Confluence username/email
            api_token: Your Confluence API token or password
            use_bearer_token: If True, use Bearer token authentication instead of Basic Auth
            exclude_config: Configuration for exclusion rules
            max_workers: Number of concurrent download workers
            download_images: Whether to download images
        """
        self.base_url = base_url.rstrip('/')
        self.exclude_config = exclude_config or ExcludeConfig()
        self.max_workers = max_workers
        self.download_images = download_images

        # Initialize Confluence client using atlassian-python-api
        self.client = ConfluenceClient(
            base_url=base_url,
            username=username,
            api_token=api_token,
            use_bearer_token=use_bearer_token,
        )

        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = False
        self.html_converter.body_width = 0  # Don't wrap lines

    @classmethod
    def from_config(cls, config: SyncConfig) -> "ConfluenceExtractor":
        """Create extractor from SyncConfig."""
        return cls(
            base_url=config.confluence_url,
            username=config.auth.username,
            api_token=config.auth.token,
            use_bearer_token=config.auth.use_bearer,
            exclude_config=config.exclude,
            max_workers=config.sync.max_workers,
            download_images=config.sync.download_images
        )

    def get_space_key_from_url(self, space_url: str) -> str:
        """Extract space key from Confluence URL"""
        # Example: https://wiki.ringcentral.com/spaces/IVA/pages/...
        parts = space_url.split('/spaces/')
        if len(parts) > 1:
            space_key = parts[1].split('/')[0]
            return space_key
        raise ValueError(f"Cannot extract space key from URL: {space_url}")

    def test_connection(self) -> bool:
        """Test if the connection and authentication work"""
        result = self.client.test_connection()
        if result:
            print("✅ Authentication successful!")
        return result

    def get_all_pages(self, space_key: str) -> List[Dict]:
        """
        Get all pages from a Confluence space

        Args:
            space_key: The space key (e.g., 'IVA')

        Returns:
            List of page objects
        """
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

    def filter_pages(self, pages: List[Dict], dry_run: bool = False) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter pages based on exclusion rules.
        
        Args:
            pages: List of page objects
            dry_run: If True, just report what would be excluded
            
        Returns:
            Tuple of (included_pages, excluded_pages)
        """
        included = []
        excluded = []
        
        for page in pages:
            should_exclude, reason = self.exclude_config.should_exclude(page)
            if should_exclude:
                excluded.append((page, reason))
                if dry_run:
                    print(f"  ⏭️  Skip: {page['title']} ({reason})")
            else:
                included.append(page)
        
        if excluded:
            print(f"📋 Filtered: {len(included)} included, {len(excluded)} excluded")
        
        return included, excluded
    
    def get_page_content(self, page_id: str) -> Optional[Dict]:
        """Get detailed content of a specific page"""
        return self.client.get_page_by_id(
            page_id=page_id,
            expand='body.storage,version,ancestors,metadata.labels,children.page'
        )

    def download_attachment(self, attachment_url: str, output_dir: Path, filename: str) -> Optional[str]:
        """
        Download an attachment from Confluence

        Args:
            attachment_url: URL to the attachment
            output_dir: Directory to save the attachment
            filename: Filename to save as

        Returns:
            Relative path to the downloaded file, or None if failed
        """
        try:
            # Create attachments directory
            attachments_dir = output_dir / 'attachments'
            attachments_dir.mkdir(parents=True, exist_ok=True)

            # Download the file using the client's session
            response = self.client.session.get(attachment_url, stream=True)
            response.raise_for_status()

            # Save the file
            file_path = attachments_dir / filename
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Return relative path
            return f'attachments/{filename}'
        except Exception as e:
            print(f"⚠️  Failed to download attachment {filename}: {e}")
            return None

    def process_images_in_html(self, html_content: str, page_id: str, output_dir: Path) -> str:
        """
        Process images in HTML content:
        1. Download images from Confluence
        2. Replace image URLs with local paths

        Args:
            html_content: HTML content from Confluence
            page_id: Page ID for fetching attachments
            output_dir: Output directory for saving images

        Returns:
            Modified HTML content with local image paths
        """
        if not self.download_images:
            return html_content
            
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find all image tags
        images = soup.find_all('img')

        for img in images:
            src = img.get('src')
            if not src:
                continue

            # Handle different types of image URLs
            if src.startswith('/'):
                # Relative URL - make it absolute
                img_url = urljoin(self.base_url, src)
            elif src.startswith('http'):
                # Already absolute
                img_url = src
            else:
                # Relative to current page
                img_url = urljoin(self.base_url, src)

            # Extract filename from URL
            # For Confluence attachments, the URL often contains the filename
            filename_match = re.search(r'/([^/]+\.(png|jpg|jpeg|gif|svg|bmp|webp))(\?|$)', img_url, re.IGNORECASE)
            if filename_match:
                filename = filename_match.group(1)
            else:
                # Generate a filename based on the image URL
                filename = f"image_{hash(img_url) & 0xFFFFFFFF}.png"

            # Download the image
            local_path = self.download_attachment(img_url, output_dir, filename)

            if local_path:
                # Update the src attribute to point to local file
                img['src'] = local_path
                print(f"  📷 Downloaded image: {filename}")

        return str(soup)

    def convert_to_markdown(self, html_content: str, page_id: str = None, output_dir: Path = None) -> str:
        """
        Convert Confluence HTML to Markdown

        Args:
            html_content: HTML content from Confluence
            page_id: Page ID (for downloading attachments)
            output_dir: Output directory (for saving images)

        Returns:
            Markdown content
        """
        # Process images if page_id and output_dir are provided
        if page_id and output_dir:
            html_content = self.process_images_in_html(html_content, page_id, output_dir)

        try:
            return self.html_converter.handle(html_content)
        except (AssertionError, Exception) as e:
            # Handle malformed HTML that html2text cannot parse
            print(f"⚠️  HTML parsing error, using fallback: {e}")
            # Fallback: strip HTML tags and return plain text
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text(separator='\n\n')
    
    def sanitize_filename(self, title: str) -> str:
        """Convert page title to valid filename"""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            title = title.replace(char, '-')
        # Remove leading/trailing spaces and dots
        title = title.strip('. ')
        # Limit length
        if len(title) > 200:
            title = title[:200]
        return title
    
    def get_page_hierarchy(self, page: Dict, depth: int = -1) -> str:
        """
        Get page hierarchy path from ancestors.
        
        Args:
            page: Page object with ancestors
            depth: Number of hierarchy levels to include
                   -1 = full hierarchy
                    0 = flat (no hierarchy)
                    1 = first-level only
                    N = first N levels
        """
        ancestors = page.get('ancestors', [])
        if not ancestors or depth == 0:
            return ''
        
        path_parts = [self.sanitize_filename(a['title']) for a in ancestors]
        
        if depth > 0:
            # Take only the first 'depth' levels
            path_parts = path_parts[:depth]
        
        return '/'.join(path_parts) if path_parts else ''

    def save_page(self, page: Dict, output_dir: Path, hierarchy_depth: int = 1) -> Optional[str]:
        """
        Save a single page as markdown file

        Args:
            page: Page object from Confluence API
            output_dir: Output directory path
            hierarchy_depth: Hierarchy depth for folder structure
                             0 = flat (no subdirs)
                             1 = first-level only (default)
                            -1 = full hierarchy
            
        Returns:
            The file path if saved successfully, None otherwise
        """
        page_id = page['id']
        title = page['title']

        # Get HTML content
        html_content = page.get('body', {}).get('storage', {}).get('value', '')
        if not html_content:
            print(f"⚠️  Skipping page '{title}' (no content)")
            return None

        # Determine file path based on hierarchy_depth
        hierarchy = self.get_page_hierarchy(page, depth=hierarchy_depth)
        if hierarchy:
            file_dir = output_dir / hierarchy
        else:
            file_dir = output_dir

        file_dir.mkdir(parents=True, exist_ok=True)

        # Convert to markdown (with image downloads)
        markdown_content = self.convert_to_markdown(html_content, page_id, file_dir)

        # Build metadata
        metadata = self.build_metadata(page)

        # Combine metadata and content
        full_content = f"{metadata}\n\n{markdown_content}"

        filename = self.sanitize_filename(title) + '.md'
        file_path = file_dir / filename

        # Save file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"✅ Saved: {file_path}")
            return str(file_path)
        except Exception as e:
            print(f"❌ Error saving {title}: {e}")
            return None

    def build_metadata(self, page: Dict) -> str:
        """Build frontmatter metadata for the page"""
        metadata_lines = ['---']

        # Basic info
        metadata_lines.append(f"title: {page['title']}")
        metadata_lines.append(f"confluence_id: {page['id']}")
        metadata_lines.append(f"confluence_url: {self.base_url}{page['_links']['webui']}")

        # Version info
        version = page.get('version', {})
        if version:
            metadata_lines.append(f"version: {version.get('number', 'unknown')}")
            metadata_lines.append(f"last_updated: {version.get('when', 'unknown')}")
            if 'by' in version:
                metadata_lines.append(f"last_updated_by: {version['by'].get('displayName', 'unknown')}")

        # Labels/tags
        labels = page.get('metadata', {}).get('labels', {}).get('results', [])
        if labels:
            label_names = [label['name'] for label in labels]
            metadata_lines.append(f"tags: [{', '.join(label_names)}]")

        # Ancestors (breadcrumb)
        ancestors = page.get('ancestors', [])
        if ancestors:
            breadcrumb = ' > '.join([a['title'] for a in ancestors])
            metadata_lines.append(f"breadcrumb: {breadcrumb}")

        metadata_lines.append('---')
        return '\n'.join(metadata_lines)

    def _save_page_worker(
        self,
        page: Dict,
        output_path: Path,
        hierarchy_depth: int,
        state_manager: Optional[SyncStateManager],
        incremental: bool
    ) -> Tuple[str, bool, Optional[str]]:
        """
        Worker function for concurrent page saving.
        
        Returns:
            Tuple of (page_title, was_saved, file_path)
        """
        title = page['title']
        page_id = page['id']
        
        # Check if incremental update is needed
        if incremental and state_manager:
            last_modified = page.get('version', {}).get('when', '')
            if not state_manager.is_updated(page_id, last_modified):
                return (title, False, None)  # Skip, not updated
        
        # Save the page
        file_path = self.save_page(page, output_path, hierarchy_depth)
        
        # Update state if saved successfully
        if file_path and state_manager:
            last_modified = page.get('version', {}).get('when', '')
            state_manager.update(page_id, last_modified, file_path, title)
        
        return (title, file_path is not None, file_path)

    def extract_space(
        self,
        space_key: str,
        output_dir: str,
        preserve_hierarchy: bool = True,
        hierarchy_depth: int = 1,  # Default to first-level if not specified
        incremental: bool = False,
        state_file: Optional[str] = None,
        dry_run: bool = False
    ):
        """
        Extract all pages from a Confluence space

        Args:
            space_key: The space key to extract
            output_dir: Directory to save markdown files
            preserve_hierarchy: Legacy flag. If False, forces hierarchy_depth=0
            hierarchy_depth: Hierarchy depth (0=flat, 1=first-level, -1=full)
            incremental: Whether to use incremental updates
            state_file: Path to state file for incremental updates
            dry_run: If True, only show what would be done
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Backward compatibility logic
        if not preserve_hierarchy:
            hierarchy_depth = 0

        # Initialize state manager if incremental
        state_manager = None
        if incremental and state_file:
            state_manager = SyncStateManager(state_file, space_key)
            state_manager.load()
            stats = state_manager.get_stats()
            if stats['last_sync']:
                print(f"📊 Last sync: {stats['last_sync']} ({stats['total_pages']} pages)")

        # Get all pages
        pages = self.get_all_pages(space_key)

        if not pages:
            print("❌ No pages found!")
            return

        # Filter pages based on exclusion rules
        included_pages, excluded_pages = self.filter_pages(pages, dry_run=dry_run)
        
        if dry_run:
            print(f"\n🔍 Dry run complete:")
            print(f"   Would sync: {len(included_pages)} pages")
            print(f"   Would skip: {len(excluded_pages)} pages")
            
            # Calculate directory statistics
            dir_stats = {}
            for page in included_pages:
                hierarchy = self.get_page_hierarchy(page, depth=hierarchy_depth)
                dir_name = hierarchy if hierarchy else "(root)"
                dir_stats[dir_name] = dir_stats.get(dir_name, 0) + 1
            
            print(f"\n📁 Directory Distribution:")
            # Sort by count (descending)
            sorted_stats = sorted(dir_stats.items(), key=lambda x: x[1], reverse=True)
            for dir_name, count in sorted_stats:
                print(f"   - {dir_name}: {count} pages")
            return

        # Save each page (with concurrency)
        print(f"\n📝 Saving {len(included_pages)} pages to {output_path}")
        
        saved_count = 0
        skipped_count = 0
        
        if self.max_workers > 1:
            # Concurrent downloads
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self._save_page_worker,
                        page,
                        output_path,
                        hierarchy_depth,
                        state_manager,
                        incremental
                    ): page
                    for page in included_pages
                }
                
                for i, future in enumerate(as_completed(futures), 1):
                    title, was_saved, file_path = future.result()
                    if was_saved:
                        saved_count += 1
                    else:
                        skipped_count += 1
                        if incremental:
                            print(f"  ⏭️  Skipped (unchanged): {title}")
                    
                    # Progress indicator
                    if i % 10 == 0:
                        print(f"  Progress: {i}/{len(included_pages)}")
        else:
            # Sequential downloads
            for i, page in enumerate(included_pages, 1):
                print(f"\n[{i}/{len(included_pages)}] Processing: {page['title']}")
                title, was_saved, file_path = self._save_page_worker(
                    page, output_path, hierarchy_depth, state_manager, incremental
                )
                if was_saved:
                    saved_count += 1
                else:
                    skipped_count += 1

        # Save state
        if state_manager:
            state_manager.save()

        # Save index
        self.save_index(included_pages, output_path, space_key)

        print(f"\n🎉 Extraction complete!")
        print(f"   Saved: {saved_count} pages")
        if skipped_count > 0:
            print(f"   Skipped (unchanged): {skipped_count} pages")
        print(f"   Excluded: {len(excluded_pages)} pages")
        print(f"   Output: {output_path}")

    def save_index(self, pages: List[Dict], output_dir: Path, space_key: str):
        """Save an index file with all pages"""
        index_path = output_dir / 'INDEX.md'

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(f"# Confluence Space: {space_key}\n\n")
            f.write(f"Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total Pages: {len(pages)}\n\n")
            f.write("## Pages\n\n")

            for page in sorted(pages, key=lambda p: p['title']):
                title = page['title']
                page_id = page['id']
                url = f"{self.base_url}{page['_links']['webui']}"
                f.write(f"- [{title}]({url}) (ID: {page_id})\n")

        print(f"✅ Index saved: {index_path}")


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Extract Confluence space to local markdown files')
    
    # Config file option
    parser.add_argument('--config', help='Path to YAML configuration file')
    
    # Legacy options (for backwards compatibility)
    parser.add_argument('--url', help='Confluence space URL or base URL')
    parser.add_argument('--space-key', help='Space key (if not in URL)')
    parser.add_argument('--username', help='Confluence username/email')
    parser.add_argument('--token', help='Confluence API token or password')
    parser.add_argument('--output', default='./confluence_export', help='Output directory')
    parser.add_argument('--flat', action='store_true', help='Save all files in flat structure (no hierarchy)')
    parser.add_argument('--bearer', action='store_true', help='Use Bearer token authentication instead of Basic Auth')
    parser.add_argument('--test', action='store_true', help='Test connection only, do not extract')
    
    # New options
    parser.add_argument('--incremental', action='store_true', help='Enable incremental updates')
    parser.add_argument('--workers', type=int, default=4, help='Number of concurrent download workers')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--exclude-title', action='append', dest='exclude_titles', help='Exclude pages matching title pattern (regex)')
    parser.add_argument('--exclude-label', action='append', dest='exclude_labels', help='Exclude pages with this label')
    parser.add_argument('--exclude-ancestor', action='append', dest='exclude_ancestors', help='Exclude pages under this parent')

    args = parser.parse_args()

    # Load configuration
    if args.config:
        # Use config file
        try:
            config = SyncConfig.from_yaml(args.config)
            print(f"📄 Loaded configuration from: {args.config}")
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            sys.exit(1)
            
        # Process each space in config
        extractor = ConfluenceExtractor.from_config(config)
        
        # Test connection
        print("🔍 Testing connection...")
        if not extractor.test_connection():
            print("\n💡 Troubleshooting tips:")
            print("   1. Check if your username and token are correct")
            print("   2. Verify environment variables are set")
            print("   3. Check if you're connected to VPN (if required)")
            sys.exit(1)
        
        if args.test:
            print("\n✅ Connection test successful!")
            sys.exit(0)
        
        # Sync each space
        for space_config in config.spaces:
            print(f"\n{'='*60}")
            print(f"📁 Syncing space: {space_config.key}")
            print(f"   Output: {space_config.output_dir}")
            print(f"   Hierarchy: {'Flat' if space_config.hierarchy_depth == 0 else ('First Level' if space_config.hierarchy_depth == 1 else 'Full')}")
            print(f"{'='*60}")
            
            extractor.extract_space(
                space_key=space_config.key,
                output_dir=space_config.output_dir,
                preserve_hierarchy=not space_config.flat,  # Used for legacy check
                hierarchy_depth=space_config.hierarchy_depth,
                incremental=config.sync.incremental,
                state_file=config.sync.state_file,
                dry_run=args.dry_run or config.sync.dry_run
            )
    else:
        # Legacy mode: use command-line arguments
        if not args.url or not args.username or not args.token:
            parser.error("--url, --username, and --token are required when not using --config")
        
        # Parse base URL
        parsed = urlparse(args.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Build exclusion config
        exclude_config = ExcludeConfig(
            titles=args.exclude_titles or [],
            labels=args.exclude_labels or [],
            ancestors=args.exclude_ancestors or []
        )

        # Initialize extractor
        extractor = ConfluenceExtractor(
            base_url,
            args.username,
            args.token,
            use_bearer_token=args.bearer,
            exclude_config=exclude_config,
            max_workers=args.workers
        )

        # Get space key
        if args.space_key:
            space_key = args.space_key
        else:
            try:
                space_key = extractor.get_space_key_from_url(args.url)
            except ValueError as e:
                print(f"❌ {e}")
                print("Please provide --space-key argument")
                sys.exit(1)

        print(f"🚀 Starting extraction...")
        print(f"   Base URL: {base_url}")
        print(f"   Space Key: {space_key}")
        print(f"   Output: {args.output}")
        print(f"   Auth Method: {'Bearer Token' if args.bearer else 'Basic Auth'}")
        print(f"   Incremental: {args.incremental}")
        print(f"   Workers: {args.workers}")
        print()

        # Test connection first
        print("🔍 Testing connection...")
        if not extractor.test_connection():
            print("\n💡 Troubleshooting tips:")
            print("   1. Check if your username and token are correct")
            print("   2. Try using --bearer flag for Bearer token authentication")
            print("   3. Verify you have access to the Confluence space")
            print("   4. Check if you're connected to VPN (if required)")
            sys.exit(1)

        if args.test:
            print("\n✅ Connection test successful! You can now run without --test flag to extract.")
            sys.exit(0)

        print()

        # Extract space
        state_file = ".sync_state.json" if args.incremental else None
        extractor.extract_space(
            space_key,
            args.output,
            preserve_hierarchy=not args.flat,
            incremental=args.incremental,
            state_file=state_file,
            dry_run=args.dry_run
        )


if __name__ == '__main__':
    main()
