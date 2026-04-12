#!/usr/bin/env python3
"""
Confluence PDF Exporter - 直接导出 PDF，无需手动提取图片
使用 Confluence 的 FlyingPDF 功能直接导出完整的 PDF 文件
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from requests import HTTPError

# Import from cptools_confluence library
from cptools_confluence import ConfluenceClient, SyncConfig

# Import local modules
try:
    from .sync_state import SyncStateManager
except ImportError:
    from sync_state import SyncStateManager



class ConfluencePDFExporter:
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
                expand='version,ancestors',
                limit=100
            )
            return pages
        except Exception as e:
            print(f"❌ Error fetching pages: {e}")
            return []
    
    def export_page_as_pdf(self, page_id: str, page_title: str, output_dir: Path) -> bool:
        """Export a single page as PDF using Confluence's FlyingPDF.

        Uses atlassian-python-api's get_page_as_pdf() so that the correct headers
        (e.g. X-Atlassian-Token: no-check for .action endpoints) are sent and
        redirects are followed. Falls back to manual request with those headers
        if the library call fails in a retryable way.
        """
        atlassian_confluence = self.client.client  # inner atlassian Confluence
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                pdf_content = atlassian_confluence.get_page_as_pdf(page_id)
                if pdf_content and len(pdf_content) > 0:
                    safe_filename = self._sanitize_filename(page_title) + '.pdf'
                    pdf_path = output_dir / safe_filename
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_content)
                    return True
                print(f"   ⚠️  Empty PDF response")
                return False
            except HTTPError as e:
                status_code = e.response.status_code if e.response else None
                if status_code == 403:
                    print(f"   ⚠️  403 Forbidden: no permission to export this page (restricted or not viewable)")
                    return False
                if status_code is not None and 400 <= status_code < 500:
                    print(f"   ⚠️  Client error: {status_code} - {e}")
                    return False
                if attempt < max_retries - 1:
                    print(f"   ⚠️  Error: {e}, retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"   ⚠️  Failed to export PDF after retries: {e}")
                return False
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  Error: {e}, retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                print(f"   ⚠️  Failed to export PDF after retries: {e}")
                return False
        return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem usage"""
        import html
        # Unescape HTML entities (e.g., &amp; -> &)
        filename = html.unescape(filename)
        # Replace invalid chars with underscore
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip('. ')
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def _get_breadcrumb(self, page: Dict) -> str:
        """Get page breadcrumb from ancestors"""
        ancestors = page.get('ancestors', [])
        breadcrumb_parts = [a.get('title', f"[id:{a.get('id', '?')}]") for a in ancestors]
        breadcrumb_parts.append(page.get('title', '[Untitled]'))
        return ' > '.join(breadcrumb_parts)

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

        path_parts = [self._sanitize_filename(a.get('title', f"id_{a.get('id', 'unknown')}")) for a in ancestors]
        
        if depth > 0:
            # Take only the first 'depth' levels
            path_parts = path_parts[:depth]
        
        return '/'.join(path_parts) if path_parts else ''

    def export_space_as_pdf(self, space_key: str, output_dir: str):
        """Export entire space to PDF files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        print(f"🚀 Starting PDF export...")
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

        # Export pages as PDF
        print(f"\n📄 Exporting {len(pages)} pages as PDF to {output_dir}\n")
        saved_count = 0

        for i, page in enumerate(pages, 1):
            title = page['title']
            page_id = page['id']
            print(f"[{i}/{len(pages)}] Exporting: {title}")

            if self.export_page_as_pdf(page_id, title, output_path):
                safe_filename = self._sanitize_filename(title) + '.pdf'
                print(f"✅ Saved: {output_path / safe_filename}")
                saved_count += 1

            # Be nice to the server
            time.sleep(0.5)

        # Create index
        self._create_index(pages, output_path)

        print(f"\n🎉 Export complete! Saved {saved_count}/{len(pages)} PDFs")
        print(f"📁 Files saved to: {output_dir}")

    def _create_index(self, pages: List[Dict], output_dir: Path):
        """Create an index file listing all pages"""
        index_path = output_dir / 'INDEX.md'

        with open(index_path, 'w', encoding='utf-8') as f:
            f.write("# Confluence Space PDF Export Index\n\n")
            f.write(f"Total pages: {len(pages)}\n\n")

            f.write("## All Pages (Alphabetical)\n\n")
            for page in sorted(pages, key=lambda p: p['title']):
                breadcrumb = self._get_breadcrumb(page)
                safe_filename = self._sanitize_filename(page['title']) + '.pdf'
                f.write(f"- [{page['title']}]({safe_filename}) - `{breadcrumb}`\n")

        print(f"✅ Index saved: {index_path}")


def main():
    import sys
    
    # Import config modules
    try:
        from .sync_config import SyncConfig
    except ImportError:
        from sync_config import SyncConfig

    parser = argparse.ArgumentParser(
        description='Export Confluence space to PDF files (includes all images and diagrams)'
    )
    
    # Config file option
    parser.add_argument('--config', help='Path to YAML configuration file')
    
    # Legacy options
    parser.add_argument('--url', help='Confluence base URL or page URL')
    parser.add_argument('--space-key', help='Space key (if not provided, will extract from URL)')
    parser.add_argument('--username', help='Confluence username/email')
    parser.add_argument('--token', help='Confluence API token')
    parser.add_argument('--output', help='Output directory')
    parser.add_argument('--bearer', action='store_true', help='Use Bearer token authentication')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    args = parser.parse_args()

    if args.config:
        # Use config file
        try:
            config = SyncConfig.from_yaml(args.config)
            print(f"📄 Loaded configuration from: {args.config}")
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            sys.exit(1)
        
        # Create exporter
        exporter = ConfluencePDFExporter(
            base_url=config.confluence_url,
            username=config.auth.username,
            api_token=config.auth.token,
            use_bearer_token=config.auth.use_bearer
        )
        
        # Test connection
        print("🔍 Testing connection...")
        if not exporter.test_connection():
            print("❌ Authentication failed!")
            sys.exit(1)
        print("✅ Authentication successful!")
        
        if args.test:
            sys.exit(0)
        
        # Export each space
        for space_config in config.spaces:
            # PDF output directory (use config directly)
            pdf_output = space_config.output_dir
            
            print(f"\n{'='*60}")
            print(f"📁 Exporting space: {space_config.key}")
            print(f"   Output: {pdf_output}")
            print(f"{'='*60}")
            
            if args.dry_run:
                pages = exporter.fetch_all_pages(space_config.key)
                # Apply exclusion filter
                excluded_count = 0
                for page in pages:
                    should_exclude, reason = config.exclude.should_exclude(page)
                    if should_exclude:
                        excluded_count += 1
                        print(f"  ⏭️  Skip: {page['title']} ({reason})")
                print(f"\n🔍 Dry run: Would export {len(pages) - excluded_count} pages, skip {excluded_count}")
            else:
                export_space_with_filter(
                    exporter, 
                    space_config.key, 
                    pdf_output, 
                    config.exclude,
                    hierarchy_depth=space_config.hierarchy_depth,
                    incremental=config.sync.incremental,
                    state_file=config.sync.state_file,
                    dry_run=args.dry_run or config.sync.dry_run,
                    max_workers=config.sync.max_workers
                )
    else:
        # Legacy mode
        if not args.url or not args.username or not args.token:
            parser.error("--url, --username, and --token are required when not using --config")

        # Extract base URL
        if '/spaces/' in args.url or '/pages/' in args.url:
            base_url = args.url.split('/spaces/')[0] if '/spaces/' in args.url else args.url.split('/wiki')[0] + '/wiki'
        else:
            base_url = args.url

        # Create exporter
        exporter = ConfluencePDFExporter(
            base_url=base_url,
            username=args.username,
            api_token=args.token,
            use_bearer_token=args.bearer
        )

        # Test mode
        if args.test:
            print("🔍 Testing connection...")
            if exporter.test_connection():
                print("✅ Connection successful!")
                if args.space_key:
                    space_key = args.space_key
                else:
                    space_key = exporter.get_space_key_from_url(args.url)
                if space_key:
                    print(f"✅ Space key: {space_key}")
                    pages = exporter.fetch_all_pages(space_key)
                    print(f"✅ Found {len(pages)} pages")
            else:
                print("❌ Connection failed!")
            return

        # Check output directory
        if not args.output:
            print("❌ --output is required for export mode")
            return

        # Get space key
        if args.space_key:
            space_key = args.space_key
        else:
            space_key = exporter.get_space_key_from_url(args.url)
            if not space_key:
                print("❌ Could not extract space key from URL. Please provide --space-key")
                return

        print(f"   Auth Method: {'Bearer Token' if args.bearer else 'Basic Auth'}")
        print()

        exporter.export_space_as_pdf(space_key, args.output)



import threading
from concurrent.futures import ThreadPoolExecutor


def _export_page_worker(
    exporter: ConfluencePDFExporter, 
    page: Dict, 
    output_path: Path, 
    hierarchy_depth: int, 
    incremental: bool, 
    state_manager: Optional[SyncStateManager], 
    lock: threading.Lock,
    progress: Optional[tuple] = None, # (counter, total, log_func)
    quiet: bool = False
):
    """Worker function for concurrent PDF export."""
    title = page['title']
    page_id = page['id']
    
    # Progress info
    current_idx = 0
    total_count = 0
    log_func = print
    if progress:
        counter, total_count, log_func = progress
        current_idx = next(counter)

    # Check incremental (read-only check)
    if incremental and state_manager:
        last_modified = page.get('version', {}).get('when', '')
        if not state_manager.is_updated(page_id, last_modified):
             # Optional: log skipped
            # if progress:
            #     log_func(f"[{current_idx}/{total_count}] ⏭️  Skipped (unchanged): {title}")
            return False

    # Determine output directory (hierarchy)
    hierarchy = exporter.get_page_hierarchy(page, depth=hierarchy_depth)
    target_dir = output_path / hierarchy if hierarchy else output_path
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Export
    if progress:
        log_func(f"[{current_idx}/{total_count}] 🔄 Exporting: {title}")
    elif not quiet:
        print(f"🔄 Exporting: {title}")
    
    if exporter.export_page_as_pdf(page_id, title, target_dir):
        safe_filename = exporter._sanitize_filename(title) + '.pdf'
        pdf_path = target_dir / safe_filename
        if not quiet and not progress:
            print(f"✅ Saved: {pdf_path}")
        
        # Update state with lock
        if state_manager:
            with lock:
                last_modified = page.get('version', {}).get('when', '')
                state_manager.update(page_id, last_modified, str(pdf_path), title)
                state_manager.save()
        return True
    
    return False


def export_space_with_filter(
    exporter: ConfluencePDFExporter, 
    space_key: str, 
    output_dir: str, 
    exclude_config,
    hierarchy_depth: int = 1,
    incremental: bool = False,
    state_file: str = ".sync_state.json",
    dry_run: bool = False,
    max_workers: int = 1
):
    """Export space with exclusion filter applied."""
    import time
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize state manager if incremental
    state_manager = None
    if incremental:
        # State file path relative to output dir
        state_file_path = output_path / state_file
        state_manager = SyncStateManager(str(state_file_path), space_key)
        state_manager.load()
        stats = state_manager.get_stats()
        if stats['last_sync']:
            print(f"📊 Last sync: {stats['last_sync']} ({stats['total_pages']} pages)")

    # Fetch all pages
    pages = exporter.fetch_all_pages(space_key)
    if not pages:
        print("❌ No pages found")
        return

    # Filter pages
    included_pages = []
    excluded_count = 0
    for page in pages:
        should_exclude, reason = exclude_config.should_exclude(page)
        if should_exclude:
            excluded_count += 1
            if dry_run:
                print(f"  ⏭️  Skip: {page['title']} ({reason})")
        else:
            included_pages.append(page)

    print(f"📋 Filtered: {len(included_pages)} included, {excluded_count} excluded")
    
    if dry_run:
        print(f"\n🔍 Dry run complete:")
        print(f"   Would sync: {len(included_pages)} pages")
        print(f"   Would skip: {len(excluded_pages) if 'excluded_pages' in locals() else excluded_count} pages") 
        
        # Calculate directory statistics
        dir_stats = {}
        for page in included_pages:
            hierarchy = exporter.get_page_hierarchy(page, depth=hierarchy_depth)
            dir_name = hierarchy if hierarchy else "(root)"
            dir_stats[dir_name] = dir_stats.get(dir_name, 0) + 1
        
        print(f"\n📁 Directory Distribution:")
        sorted_stats = sorted(dir_stats.items(), key=lambda x: x[1], reverse=True)
        for dir_name, count in sorted_stats:
            print(f"   - {dir_name}: {count} pages")
        return

    # Export pages as PDF
    print(f"\n📄 Exporting {len(included_pages)} pages as PDF to {output_dir}")
    print(f"🚀 Concurrency: {max_workers} threads\n")
    
    saved_count = 0
    
    lock = threading.Lock()
    
    
    # Import tqdm for progress bar
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False

    # Progress helpers
    import itertools
    total_pages = len(included_pages)
    counter = itertools.count(1)
    
    def log_progress(msg):
        if use_tqdm:
            tqdm.write(msg)
        else:
            print(msg)

    if max_workers > 1:
        from concurrent.futures import as_completed
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            # Submit all tasks
            for page in included_pages:
                future = executor.submit(
                    _export_page_worker,
                    exporter,
                    page,
                    output_path,
                    hierarchy_depth,
                    incremental,
                    state_manager,
                    lock,
                    (counter, total_pages, print if not use_tqdm else log_progress),
                    use_tqdm # quiet param
                )
                futures.append(future)
            
            # Process results with progress bar
            iterator = as_completed(futures)
            if use_tqdm:
                iterator = tqdm(iterator, total=total_pages, unit="page", desc="Exporting")
            
            for future in iterator:
                try:
                    if future.result():
                        saved_count += 1
                except Exception as e:
                    print(f"\n❌ Worker error: {e}")
    else:
        # Sequential fallback
        iterator = included_pages
        if use_tqdm:
            iterator = tqdm(included_pages, unit="page", desc="Exporting")
            
        for i, page in enumerate(iterator):
             # Using shared counter logic for consistency
             progress_info = (counter, total_pages, log_progress)
                 
             if _export_page_worker(exporter, page, output_path, hierarchy_depth, incremental, state_manager, lock, progress=progress_info, quiet=use_tqdm):
                 saved_count += 1
                 if not use_tqdm:
                     time.sleep(0.5)

    # Save state
    if state_manager:
        state_manager.save()

    # Create index
    exporter._create_index(included_pages, output_path)

    print(f"\n🎉 Export complete! Saved {saved_count} PDFs")
    print(f"📁 Files saved to: {output_dir}")


if __name__ == '__main__':
    main()

