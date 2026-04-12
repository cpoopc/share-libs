#!/usr/bin/env python3
"""
OpenAPI to Confluence Uploader

Converts OpenAPI specification files to Markdown and uploads to Confluence.
"""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .markdown_uploader import MarkdownUploader, UploadConfig, UploadResult
from .openapi_converter import OpenAPIConverter, ConvertOptions


def upload_openapi(
    openapi_path: Path,
    uploader: MarkdownUploader,
    space_key: Optional[str] = None,
    parent_id: Optional[str] = None,
    page_id: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
) -> UploadResult:
    """
    Convert OpenAPI file to Markdown and upload to Confluence.
    
    Args:
        openapi_path: Path to OpenAPI YAML/JSON file
        uploader: Configured MarkdownUploader instance
        space_key: Target Confluence space
        parent_id: Parent page ID for new pages
        page_id: Target page ID for updates
        force: Force upload ignoring hash check
        dry_run: Preview mode without actual upload
        
    Returns:
        UploadResult with page info and status
    """
    openapi_path = Path(openapi_path)
    
    if not openapi_path.exists():
        return UploadResult(
            success=False,
            action="error",
            md_path=str(openapi_path),
            error=f"OpenAPI file not found: {openapi_path}"
        )
    
    # Convert OpenAPI to Markdown
    print(f"📄 Converting OpenAPI: {openapi_path.name}")
    
    try:
        converter = OpenAPIConverter(ConvertOptions(
            include_examples=True,
            include_schemas=True,
            include_toc=True,
            group_by_tag=True,
        ))
        result = converter.convert_file(openapi_path)
    except Exception as e:
        return UploadResult(
            success=False,
            action="error",
            md_path=str(openapi_path),
            error=f"Failed to convert OpenAPI: {e}"
        )
    
    print(f"  ✅ Converted: {result.title} (v{result.version})")
    print(f"  📊 Endpoints: {result.endpoints_count}")
    
    # Create frontmatter
    frontmatter = f"""---
title: "{result.title}"
openapi_version: "{result.version}"
source_file: "{openapi_path.name}"
---

"""
    
    markdown_content = frontmatter + result.markdown
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.md',
        delete=False,
        encoding='utf-8'
    ) as tmp_file:
        tmp_file.write(markdown_content)
        tmp_path = Path(tmp_file.name)
    
    try:
        # Upload using existing Markdown uploader
        upload_result = uploader.upload_file(
            md_path=tmp_path,
            space_key=space_key,
            parent_id=parent_id,
            page_id=page_id,
            force=force,
            dry_run=dry_run,
        )
        
        # Update result with original path
        upload_result.md_path = str(openapi_path)
        return upload_result
        
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Upload OpenAPI specification to Confluence"
    )
    parser.add_argument(
        "--openapi", "-o",
        required=True,
        help="Path to OpenAPI YAML/JSON file"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml"
    )
    parser.add_argument(
        "--space", "-s",
        help="Target Confluence space"
    )
    parser.add_argument(
        "--parent", "-p",
        help="Parent page ID"
    )
    parser.add_argument(
        "--page-id",
        help="Target page ID (for updates)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force upload"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview mode"
    )
    parser.add_argument(
        "--title-strategy",
        choices=["keep-page-title", "use-doc-title", "fail-on-title-mismatch"],
        help="How to handle title mismatches when updating an existing page",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-upload readback verification",
    )
    parser.add_argument(
        "--mermaid-artifact-dir",
        help="Directory to persist rendered Mermaid artifacts",
    )
    
    args = parser.parse_args()
    
    # Load config and create uploader (same as markdown_uploader.py)
    if args.config:
        from cptools_confluence import SyncConfig
        from cptools_confluence import ConfluenceClient
        
        sync_config = SyncConfig.from_yaml(args.config)
        client = ConfluenceClient(
            base_url=sync_config.confluence_url,
            username=sync_config.auth.username,
            api_token=sync_config.auth.token,
            use_bearer_token=sync_config.auth.use_bearer,
        )
        upload_config = UploadConfig(
            default_space=args.space or (sync_config.spaces[0].key if sync_config.spaces else ""),
            root_page_id=args.parent,
            title_mismatch_strategy=args.title_strategy or "keep-page-title",
            verify_upload=not args.no_verify,
            mermaid_artifact_dir=args.mermaid_artifact_dir,
        )
    else:
        import os
        from cptools_confluence import ConfluenceClient
        
        base_url = os.environ.get('CONFLUENCE_URL', 'https://wiki.example.com')
        username = os.environ.get('CONFLUENCE_USERNAME', '')
        token = os.environ.get('CONFLUENCE_TOKEN', '')
        
        if not username or not token:
            print("❌ CONFLUENCE_USERNAME and CONFLUENCE_TOKEN required")
            sys.exit(1)
        
        client = ConfluenceClient(
            base_url=base_url,
            username=username,
            api_token=token,
        )
        upload_config = UploadConfig(
            default_space=args.space or 'IVA',
            root_page_id=args.parent,
            title_mismatch_strategy=args.title_strategy or "keep-page-title",
            verify_upload=not args.no_verify,
            mermaid_artifact_dir=args.mermaid_artifact_dir,
        )
    
    # Test connection
    print("🔍 Testing connection...")
    if not client.test_connection():
        print("❌ Connection failed")
        sys.exit(1)
    
    # Create uploader and upload
    uploader = MarkdownUploader(client, upload_config)
    
    result = upload_openapi(
        openapi_path=Path(args.openapi),
        uploader=uploader,
        space_key=args.space,
        parent_id=args.parent,
        page_id=args.page_id,
        force=args.force,
        dry_run=args.dry_run,
    )
    
    if not result.success:
        print(f"❌ Upload failed: {result.error}")
        sys.exit(1)
    
    print(f"\n✅ {result.action}: {result.title}")
    if result.page_url:
        print(f"   URL: {result.page_url}")


if __name__ == "__main__":
    main()
