#!/usr/bin/env python3
"""
Markdown Uploader for Confluence

Main entry point for uploading Markdown files to Confluence.
Supports single file and directory uploads with incremental detection.
"""

import sys
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Import from cptools_confluence library
from cptools_confluence import ConfluenceClient

from .image_handler import ImageHandler
from .md_converter import ConverterOptions, MDConverter
from .upload_state import UploadState


@dataclass
class UploadConfig:
    """Upload configuration."""
    default_space: str
    root_page_id: Optional[str] = None
    state_file: str = ".upload_state.json"

    # Converter options
    heading_anchors: bool = True
    skip_title_heading: bool = True
    render_mermaid: bool = False
    render_drawio: bool = False
    alignment: str = "center"
    max_image_width: Optional[int] = None

    # Behavior options
    update_frontmatter: bool = True
    check_conflicts: bool = True
    title_mismatch_strategy: str = "keep-page-title"  # keep-page-title | use-doc-title | fail-on-title-mismatch
    verify_upload: bool = True
    mermaid_artifact_dir: Optional[str] = None


@dataclass
class UploadResult:
    """Upload result."""
    success: bool
    action: str  # "created" | "updated" | "skipped" | "error"
    md_path: str
    page_id: Optional[str] = None
    page_url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None


class MarkdownUploader:
    """
    Markdown file uploader to Confluence.

    Supports:
    - Single file upload/update
    - Directory batch upload (preserving hierarchy)
    - Incremental uploads (based on content hash)
    - Image auto-upload
    """

    def __init__(
        self,
        client: ConfluenceClient,
        config: UploadConfig,
    ):
        """
        Initialize the uploader.

        Args:
            client: Confluence API client
            config: Upload configuration
        """
        self.client = client
        self.config = config
        self.converter = MDConverter(ConverterOptions(
            heading_anchors=config.heading_anchors,
            skip_title_heading=config.skip_title_heading,
            render_mermaid=config.render_mermaid,
            render_drawio=config.render_drawio,
            alignment=config.alignment,
            max_image_width=config.max_image_width,
            mermaid_output_dir=Path(config.mermaid_artifact_dir) if config.mermaid_artifact_dir else None,
        ))
        self.image_handler = ImageHandler(client)
        self.state = UploadState(config.state_file)

    def upload_file(
        self,
        md_path: Path,
        space_key: Optional[str] = None,
        parent_id: Optional[str] = None,
        page_id: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> UploadResult:
        """
        Upload a single Markdown file to Confluence.

        Args:
            md_path: Path to the Markdown file
            space_key: Target space key (optional, uses frontmatter or config)
            parent_id: Parent page ID (optional, uses frontmatter or config)
            page_id: Target page ID for update (optional, overrides frontmatter)
            force: Force upload, ignore hash check
            dry_run: Preview mode, don't actually upload

        Returns:
            UploadResult with page info and status
        """
        md_path = Path(md_path)

        if not md_path.exists():
            return UploadResult(
                success=False,
                action="error",
                md_path=str(md_path),
                error=f"File not found: {md_path}"
            )

        # Read file content
        try:
            content = md_path.read_text(encoding='utf-8')
        except Exception as e:
            return UploadResult(
                success=False,
                action="error",
                md_path=str(md_path),
                error=f"Failed to read file: {e}"
            )

        # Parse frontmatter
        frontmatter, body = self.converter.parse_frontmatter(content)

        # Determine space key
        target_space = (
            frontmatter.get('confluence_space') or
            space_key or
            self.config.default_space
        )

        # Determine parent page
        target_parent = (
            frontmatter.get('parent_id') or
            parent_id or
            self.config.root_page_id
        )

        # Convert to CSF (also collects attachments)
        convert_result = self.converter.convert(body, md_path.parent)
        csf_content = convert_result.csf_content
        title = frontmatter.get('title') or convert_result.title

        # Check if content changed (incremental, includes drawio attachments)
        content_hash = self._compute_content_hash(body, convert_result.drawio_attachments)
        if not force and not self.state.is_content_changed(str(md_path), content_hash):
            return UploadResult(
                success=True,
                action="skipped",
                md_path=str(md_path),
                title=title,
            )

        # Determine action: create or update
        # If page_id is provided via parameter, use it directly
        if page_id:
            action = "update"
            target_page_id = page_id
        else:
            action, target_page_id = self._determine_page_action(
                md_path, frontmatter, target_space
            )

        existing_version: Optional[int] = None
        if action == "update" and target_page_id:
            page_info = self.client.get_page_by_id(
                target_page_id,
                expand="space,version,body.storage",
            )
            if page_info:
                existing_version = page_info.get("version", {}).get("number")
                existing_title = page_info.get("title")
                if existing_title and existing_title != title:
                    mismatch = self._resolve_title_mismatch(existing_title, title)
                    if mismatch is not None:
                        return mismatch
                    title = self._apply_title_mismatch_strategy(existing_title, title)
                if not target_space:
                    target_space = page_info.get("space", {}).get("key") or target_space

        self._print_upload_plan(
            action=action,
            title=title,
            space_key=target_space,
            parent_id=target_parent,
            page_id=target_page_id,
            dry_run=dry_run,
            convert_result=convert_result,
        )

        if dry_run:
            return UploadResult(
                success=True,
                action=f"would_{action}",
                md_path=str(md_path),
                title=title,
            )

        try:
            if action == "create":
                # Create new page
                result = self.client.create_page(
                    space=target_space,
                    title=title,
                    body=csf_content,
                    parent_id=target_parent,
                )
                target_page_id = result['id']
                print(f"  ✅ Created: {title}")
            else:
                # Update existing page
                result = self.client.update_page(
                    page_id=target_page_id,
                    title=title,
                    body=csf_content,
                )
                print(f"  ✅ Updated: {title}")

            # Upload images (including rendered Mermaid diagrams)
            # Note: PlantUML uses Confluence macro directly, no image upload needed
            all_images = list(convert_result.images)
            if convert_result.mermaid_images:
                all_images.extend(convert_result.mermaid_images)

            if all_images:
                image_map = self.image_handler.upload_images(
                    page_id=target_page_id,
                    images=all_images,
                    base_path=md_path.parent,
                )
                # Note: Images need to be uploaded, then page content updated with correct refs
                if image_map:
                    updated_csf = self.image_handler.update_image_references(
                        csf_content, image_map
                    )
                    # Update page again with correct image references
                    self.client.update_page(
                        page_id=target_page_id,
                        title=title,
                        body=updated_csf,
                        minor_edit=True,
                    )

            # Upload drawio attachments (always create new version)
            if convert_result.drawio_attachments:
                for file_path, _, filename in convert_result.drawio_attachments:
                    self.client.upload_attachment(
                        page_id=target_page_id,
                        file_path=str(file_path),
                        filename=filename,
                        content_type="application/vnd.jgraph.mxfile",
                    )

                # Inject attachment revisions into drawio macros
                csf_with_revisions = self._inject_drawio_revisions(
                    csf_content,
                    target_page_id,
                    convert_result.drawio_attachments,
                )
                if csf_with_revisions != csf_content:
                    self.client.update_page(
                        page_id=target_page_id,
                        title=title,
                        body=csf_with_revisions,
                        minor_edit=True,
                    )
                    csf_content = csf_with_revisions

            # Get page URL
            page_url = f"{self.client.base_url}/pages/{target_page_id}"
            if 'id' in result:
                page_info = self.client.get_page_by_id(target_page_id)
                if page_info and '_links' in page_info:
                    page_url = self.client.base_url + page_info['_links'].get('webui', '')

            verification_error = None
            if self.config.verify_upload:
                verification_error = self._verify_page_upload(
                    page_id=target_page_id,
                    action=action,
                    expected_title=title,
                    previous_version=existing_version,
                    expect_mermaid_rendered=bool(convert_result.mermaid_images),
                    expected_drawio_attachments=[filename for _, _, filename in convert_result.drawio_attachments],
                )
                if verification_error:
                    return UploadResult(
                        success=False,
                        action="error",
                        md_path=str(md_path),
                        page_id=target_page_id,
                        page_url=page_url,
                        title=title,
                        error=verification_error,
                    )

            # Update state
            remote_version = self.client.get_page_version(target_page_id)
            self.state.set_mapping(
                md_path=str(md_path),
                page_id=target_page_id,
                space_key=target_space,
                title=title,
                content_hash=content_hash,
                remote_version=remote_version,
            )
            self.state.save()

            # Update frontmatter if configured
            if self.config.update_frontmatter:
                self._update_frontmatter(md_path, target_page_id, target_space, remote_version)

            return UploadResult(
                success=True,
                action="created" if action == "create" else "updated",
                md_path=str(md_path),
                page_id=target_page_id,
                page_url=page_url,
                title=title,
            )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return UploadResult(
                success=False,
                action="error",
                md_path=str(md_path),
                title=title,
                error=str(e),
            )

    def _apply_title_mismatch_strategy(self, existing_title: str, doc_title: str) -> str:
        strategy = self.config.title_mismatch_strategy
        if strategy == "use-doc-title":
            print(f"  ⚠️ Title mismatch; using document title: {doc_title}")
            return doc_title
        print(f"  ⚠️ Title mismatch; keeping existing page title: {existing_title}")
        return existing_title

    def _resolve_title_mismatch(self, existing_title: str, doc_title: str) -> Optional[UploadResult]:
        if self.config.title_mismatch_strategy == "fail-on-title-mismatch":
            return UploadResult(
                success=False,
                action="error",
                md_path="",
                title=doc_title,
                error=(
                    f"Title mismatch: remote page title is '{existing_title}' "
                    f"but document title is '{doc_title}'"
                ),
            )
        return None

    def _print_upload_plan(
        self,
        *,
        action: str,
        title: str,
        space_key: Optional[str],
        parent_id: Optional[str],
        page_id: Optional[str],
        dry_run: bool,
        convert_result: Any,
    ) -> None:
        prefix = "[DRY-RUN]" if dry_run else "[PLAN]"
        print(f"  {prefix} Action: {action}")
        print(f"  {prefix} Target title: {title}")
        if space_key:
            print(f"  {prefix} Target space: {space_key}")
        if page_id:
            print(f"  {prefix} Target page id: {page_id}")
        elif parent_id:
            print(f"  {prefix} Target parent: {parent_id}")
        print(f"  {prefix} Mermaid blocks rendered: {len(convert_result.mermaid_images)}")
        print(f"  {prefix} Draw.io attachments: {len(convert_result.drawio_attachments)}")
        print(f"  {prefix} Local images: {len(convert_result.images)}")
        if convert_result.mermaid_images:
            for image_path in convert_result.mermaid_images:
                print(f"  {prefix} Mermaid artifact: {Path(image_path).resolve()}")

    def _verify_page_upload(
        self,
        *,
        page_id: str,
        action: str,
        expected_title: str,
        previous_version: Optional[int],
        expect_mermaid_rendered: bool,
        expected_drawio_attachments: List[str],
    ) -> Optional[str]:
        page = self.client.get_page_by_id(page_id, expand="body.storage,version")
        if not page:
            return f"Upload verification failed: page {page_id} could not be read back"

        page_title = page.get("title", "")
        if page_title != expected_title:
            return (
                "Upload verification failed: page title mismatch after upload "
                f"(expected '{expected_title}', got '{page_title}')"
            )

        version = page.get("version", {}).get("number", 0)
        if action == "create":
            if version < 1:
                return "Upload verification failed: created page has invalid version"
        elif previous_version is not None and version <= previous_version:
            return (
                "Upload verification failed: page version did not advance "
                f"(previous={previous_version}, current={version})"
            )

        body = page.get("body", {}).get("storage", {}).get("value", "")
        if expect_mermaid_rendered and ("```mermaid" in body or 'language-mermaid' in body):
            return "Upload verification failed: Mermaid block still present in storage body"

        if expected_drawio_attachments:
            attachments = self.client.get_attachments(page_id)
            attachment_names = {att.get("title", "") for att in attachments}
            missing = sorted(name for name in expected_drawio_attachments if name not in attachment_names)
            if missing:
                return (
                    "Upload verification failed: missing Draw.io attachment(s): "
                    + ", ".join(missing)
                )

        print(f"  ✅ Verification passed: page {page_id} version {version}")
        return None

    def _determine_page_action(
        self,
        md_path: Path,
        frontmatter: Dict[str, Any],
        space_key: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Determine if we should create or update a page.

        Returns:
            Tuple of (action: "create"|"update", page_id: Optional[str])
        """
        # 1. Check frontmatter for confluence_id
        page_id = frontmatter.get('confluence_id')
        if page_id:
            # Verify page exists
            page = self.client.get_page_by_id(page_id)
            if page:
                return ("update", page_id)

        # 2. Check state mapping
        page_id = self.state.get_page_id(str(md_path))
        if page_id:
            page = self.client.get_page_by_id(page_id)
            if page:
                return ("update", page_id)

        # 3. Search by title
        title = frontmatter.get('title')
        if title:
            page = self.client.get_page_by_title(space_key, title)
            if page:
                return ("update", page.get('id'))

        # 4. Create new page
        return ("create", None)

    def _compute_content_hash(
        self,
        body: str,
        drawio_attachments: List[Tuple[Path, str, str]],
    ) -> str:
        """Compute hash including drawio attachment contents."""
        parts = [body]
        for file_path, _, _ in drawio_attachments:
            try:
                content = file_path.read_bytes()
                parts.append(content.hex())
            except Exception as e:
                print(f"  ⚠️ Failed to read drawio file for hashing: {file_path} ({e})")
        return UploadState.compute_hash("\n".join(parts))

    def _update_frontmatter(
        self,
        md_path: Path,
        page_id: str,
        space_key: str,
        version: int,
    ) -> None:
        """Update the Markdown file's frontmatter with Confluence info."""
        try:
            self.converter.update_frontmatter(md_path, {
                'confluence_id': page_id,
                'confluence_space': space_key,
                'version': version,
                'last_synced': datetime.now().isoformat(),
            })
        except Exception as e:
            print(f"  ⚠️ Failed to update frontmatter: {e}")

    def _inject_drawio_revisions(
        self,
        csf_content: str,
        page_id: str,
        drawio_attachments: List[Tuple[Path, str, str]],
    ) -> str:
        """Inject drawio attachment revision numbers into macros."""
        updated = csf_content

        for _, diagram_name, filename in drawio_attachments:
            revision = self._get_attachment_revision(page_id, filename)
            if revision is None:
                continue

            pattern = (
                r'(<ac:structured-macro[^>]*ac:name="drawio"[^>]*>.*?'
                r'<ac:parameter ac:name="diagramName">' + re.escape(diagram_name) + r'</ac:parameter>)'
                r'(.*?</ac:structured-macro>)'
            )

            def repl(match):
                head = match.group(1)
                tail = match.group(2)
                if 'ac:name="revision"' in head or 'ac:name="revision"' in tail:
                    return match.group(0)
                revision_param = f'<ac:parameter ac:name="revision">{revision}</ac:parameter>'
                return head + revision_param + tail

            updated = re.sub(pattern, repl, updated, flags=re.DOTALL)

        return updated

    def _get_attachment_revision(self, page_id: str, filename: str) -> Optional[int]:
        """Get attachment revision number by filename."""
        try:
            result = self.client.client.get_attachments_from_content(
                page_id,
                filename=filename,
                expand="version",
            )
            items = result.get("results", []) if isinstance(result, dict) else result
            if not items:
                return None
            return items[0].get("version", {}).get("number")
        except Exception as e:
            print(f"  ⚠️ Failed to fetch attachment version for {filename}: {e}")
            return None

    def upload_directory(
        self,
        dir_path: Path,
        space_key: Optional[str] = None,
        root_page_id: Optional[str] = None,
        preserve_hierarchy: bool = True,
        force: bool = False,
        dry_run: bool = False,
    ) -> List[UploadResult]:
        """
        Upload all Markdown files in a directory.

        Directory structure mapping:
        - index.md / README.md → Parent page for directory
        - Other .md files → Child pages
        - Subdirectories → Recursive processing

        Args:
            dir_path: Directory path
            space_key: Target space key
            root_page_id: Root parent page ID
            preserve_hierarchy: Keep directory structure as page hierarchy
            force: Force upload all files
            dry_run: Preview mode

        Returns:
            List of upload results
        """
        dir_path = Path(dir_path)
        target_space = space_key or self.config.default_space
        target_root = root_page_id or self.config.root_page_id

        if not dir_path.is_dir():
            print(f"❌ Not a directory: {dir_path}")
            return []

        results: List[UploadResult] = []

        # Find all markdown files
        md_files = sorted(dir_path.rglob('*.md'))

        if not md_files:
            print(f"⚠️ No Markdown files found in {dir_path}")
            return []

        print(f"\n📂 Uploading {len(md_files)} files from {dir_path}")

        # Build hierarchy for proper ordering
        file_hierarchy = self._build_file_hierarchy(md_files, dir_path)

        # Upload in order (parents first)
        for md_file, parent_id in file_hierarchy:
            print(f"\n[{len(results) + 1}/{len(md_files)}] {md_file.relative_to(dir_path)}")

            result = self.upload_file(
                md_path=md_file,
                space_key=target_space,
                parent_id=parent_id or target_root,
                force=force,
                dry_run=dry_run,
            )
            results.append(result)

        # Summary
        created = sum(1 for r in results if r.action == "created")
        updated = sum(1 for r in results if r.action == "updated")
        skipped = sum(1 for r in results if r.action == "skipped")
        errors = sum(1 for r in results if r.action == "error")

        print(f"\n📊 Upload Summary:")
        print(f"   Created: {created}")
        print(f"   Updated: {updated}")
        print(f"   Skipped: {skipped}")
        print(f"   Errors:  {errors}")

        return results

    def _build_file_hierarchy(
        self,
        md_files: List[Path],
        base_dir: Path,
    ) -> List[Tuple[Path, Optional[str]]]:
        """
        Build file hierarchy for ordered uploads.

        Returns list of (file_path, parent_page_id) tuples.
        """
        # For now, simple flat list - parent handling is done via frontmatter
        # TODO: Implement proper hierarchy building with index.md handling
        return [(f, None) for f in md_files]


def _load_upload_overrides(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f) or {}

    upload_config = raw_config.get('upload', {})
    converter = upload_config.get('converter', {})
    behavior = upload_config.get('behavior', {})

    return {
        "default_space": upload_config.get("default_space"),
        "root_page_id": upload_config.get("root_page_id"),
        "state_file": upload_config.get("state_file", ".upload_state.json"),
        "heading_anchors": converter.get("heading_anchors", True),
        "skip_title_heading": converter.get("skip_title_heading", True),
        "render_mermaid": converter.get("render_mermaid", False),
        "render_drawio": converter.get("render_drawio", False),
        "alignment": converter.get("alignment", "center"),
        "max_image_width": converter.get("max_image_width"),
        "update_frontmatter": behavior.get("update_frontmatter", True),
        "check_conflicts": behavior.get("check_conflicts", True),
        "title_mismatch_strategy": behavior.get("title_mismatch_strategy", "keep-page-title"),
        "verify_upload": behavior.get("verify_upload", True),
        "mermaid_artifact_dir": behavior.get("mermaid_artifact_dir"),
    }


def main():
    """CLI entry point for Markdown uploader."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Upload Markdown files to Confluence'
    )

    parser.add_argument('--file', '-f', help='Single Markdown file to upload')
    parser.add_argument('--dir', '-d', help='Directory of Markdown files to upload')
    parser.add_argument('--space', '-s', help='Target Confluence space key')
    parser.add_argument('--parent', '-p', help='Parent page ID (for new pages)')
    parser.add_argument('--page-id', help='Target page ID (for updating existing page)')
    parser.add_argument('--config', '-c', help='Configuration file path')
    parser.add_argument('--force', action='store_true', help='Force upload (ignore hash)')
    parser.add_argument('--dry-run', action='store_true', help='Preview mode')
    parser.add_argument('--no-update-frontmatter', action='store_true',
                        help='Do not update source file frontmatter')
    parser.add_argument('--render-mermaid', action='store_true',
                        help='Render Mermaid diagrams to PNG images (requires mermaid-cli)')
    parser.add_argument('--render-drawio', action='store_true',
                        help='Convert Draw.io blocks to Confluence macros and upload .drawio attachments')
    parser.add_argument(
        '--title-strategy',
        choices=['keep-page-title', 'use-doc-title', 'fail-on-title-mismatch'],
        help='How to handle title mismatches when updating an existing page',
    )
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip post-upload readback verification',
    )
    parser.add_argument(
        '--mermaid-artifact-dir',
        help='Directory to persist rendered Mermaid artifacts',
    )

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.error("Either --file or --dir is required")

    config_overrides = _load_upload_overrides(args.config) if args.config else {}

    # Load config
    if args.config:
        from cptools_confluence import SyncConfig

        sync_config = SyncConfig.from_yaml(args.config)
        client = ConfluenceClient(
            base_url=sync_config.confluence_url,
            username=sync_config.auth.username,
            api_token=sync_config.auth.token,
            use_bearer_token=sync_config.auth.use_bearer,
        )
        upload_config = UploadConfig(
            default_space=(
                args.space
                or config_overrides.get("default_space")
                or (sync_config.spaces[0].key if sync_config.spaces else "")
            ),
            root_page_id=args.parent or config_overrides.get("root_page_id"),
            state_file=config_overrides.get("state_file", ".upload_state.json"),
            heading_anchors=config_overrides.get("heading_anchors", True),
            skip_title_heading=config_overrides.get("skip_title_heading", True),
            render_mermaid=args.render_mermaid or config_overrides.get("render_mermaid", False),
            render_drawio=args.render_drawio or config_overrides.get("render_drawio", False),
            alignment=config_overrides.get("alignment", "center"),
            max_image_width=config_overrides.get("max_image_width"),
            update_frontmatter=False if args.no_update_frontmatter else config_overrides.get("update_frontmatter", True),
            check_conflicts=config_overrides.get("check_conflicts", True),
            title_mismatch_strategy=args.title_strategy or config_overrides.get("title_mismatch_strategy", "keep-page-title"),
            verify_upload=False if args.no_verify else config_overrides.get("verify_upload", True),
            mermaid_artifact_dir=args.mermaid_artifact_dir or config_overrides.get("mermaid_artifact_dir"),
        )
    else:
        # Require environment variables
        import os
        base_url = os.environ.get('CONFLUENCE_URL', 'https://wiki.example.com')
        username = os.environ.get('CONFLUENCE_USERNAME', '')
        token = os.environ.get('CONFLUENCE_TOKEN', '')

        if not username or not token:
            print("❌ CONFLUENCE_USERNAME and CONFLUENCE_TOKEN environment variables required")
            sys.exit(1)

        client = ConfluenceClient(
            base_url=base_url,
            username=username,
            api_token=token,
        )
        upload_config = UploadConfig(
            default_space=args.space or 'IVA',
            root_page_id=args.parent,
            update_frontmatter=not args.no_update_frontmatter,
            render_mermaid=args.render_mermaid,
            render_drawio=args.render_drawio,
            title_mismatch_strategy=args.title_strategy or 'keep-page-title',
            verify_upload=not args.no_verify,
            mermaid_artifact_dir=args.mermaid_artifact_dir,
        )

    # Test connection
    print("🔍 Testing connection...")
    if not client.test_connection():
        print("❌ Connection failed")
        sys.exit(1)

    # Create uploader
    uploader = MarkdownUploader(client, upload_config)

    # Execute upload
    if args.file:
        result = uploader.upload_file(
            md_path=Path(args.file),
            space_key=args.space,
            parent_id=args.parent,
            page_id=args.page_id,
            force=args.force,
            dry_run=args.dry_run,
        )
        if not result.success:
            print(f"❌ Upload failed: {result.error}")
            sys.exit(1)
    else:
        results = uploader.upload_directory(
            dir_path=Path(args.dir),
            space_key=args.space,
            root_page_id=args.parent,
            force=args.force,
            dry_run=args.dry_run,
        )
        errors = [r for r in results if r.action == "error"]
        if errors:
            print(f"\n❌ {len(errors)} errors occurred")
            sys.exit(1)

    print("\n✅ Done!")


if __name__ == '__main__':
    main()
