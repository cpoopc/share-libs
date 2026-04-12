#!/usr/bin/env python3
"""
Markdown to Confluence Storage Format Converter

Converts Markdown content to Confluence Storage Format (CSF).
Handles frontmatter parsing and various Markdown elements.
"""

import json
import hashlib
import xml.etree.ElementTree as ET
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import frontmatter
import markdown
from bs4 import BeautifulSoup

from .mermaid_renderer import MermaidRenderer, MermaidConfig
# PlantUML is rendered using Confluence PlantUML macro, no local renderer needed


@dataclass
class ConverterOptions:
    """Conversion options."""
    heading_anchors: bool = True
    skip_title_heading: bool = True
    render_mermaid: bool = False
    render_drawio: bool = False
    alignment: str = "center"
    max_image_width: Optional[int] = None
    mermaid_output_dir: Optional[Path] = None  # Directory for rendered mermaid images


@dataclass
class ConvertResult:
    """Conversion result."""
    csf_content: str
    title: str
    images: List[Path] = field(default_factory=list)
    attachments: List[Path] = field(default_factory=list)
    mermaid_images: List[Path] = field(default_factory=list)  # Rendered mermaid diagrams
    # plantuml_images removed - PlantUML now uses Confluence macro directly
    drawio_attachments: List[Tuple[Path, str, str]] = field(default_factory=list)


class MDConverter:
    """
    Markdown to Confluence Storage Format (CSF) converter.

    Converts Markdown content including:
    - Headings, paragraphs, lists
    - Code blocks with language hints
    - Tables
    - Images (local references)
    - Admonitions/alerts
    """

    # Admonition type mapping
    ADMONITION_MAP = {
        'NOTE': 'info',
        'TIP': 'tip',
        'WARNING': 'warning',
        'CAUTION': 'note',
        'IMPORTANT': 'warning',
    }

    def __init__(self, options: Optional[ConverterOptions] = None):
        """Initialize the converter."""
        self.options = options or ConverterOptions()

        # Initialize markdown converter with extensions
        self._md_extensions = [
            'tables',
            'fenced_code',
            'toc',
        ]
        self.md = markdown.Markdown(extensions=self._md_extensions)

        # Initialize Mermaid renderer if enabled
        self._mermaid_renderer: Optional[MermaidRenderer] = None
        if self.options.render_mermaid:
            self._mermaid_renderer = MermaidRenderer(
                output_dir=self.options.mermaid_output_dir
            )

        # PlantUML uses Confluence macro directly, no renderer needed

    def convert(
        self,
        markdown_content: str,
        base_path: Optional[Path] = None,
    ) -> ConvertResult:
        """
        Convert Markdown to Confluence Storage Format.

        Args:
            markdown_content: Markdown content (without frontmatter)
            base_path: Base path for resolving relative image paths

        Returns:
            ConvertResult with CSF content and referenced resources
        """
        # Reset the markdown converter
        self.md.reset()

        # Extract title from first heading
        title = self._extract_title(markdown_content)

        # Optionally skip the first H1 heading
        if self.options.skip_title_heading:
            markdown_content = self._remove_first_heading(markdown_content)

        # Pre-process admonitions
        markdown_content = self._process_admonitions(markdown_content)

        # Pre-process Draw.io blocks (convert to macros + collect attachments)
        drawio_attachments: List[Tuple[Path, str, str]] = []
        if self.options.render_drawio:
            markdown_content, drawio_attachments = self._process_drawio_blocks(
                markdown_content, base_path
            )

        # Pre-process Mermaid diagrams (render to images when explicitly enabled)
        mermaid_images: List[Path] = []
        if self.options.render_mermaid and self._mermaid_renderer:
            markdown_content, mermaid_images = self._process_mermaid_blocks(markdown_content)

        # Pre-process PlantUML diagrams (convert to Confluence macro placeholders)
        markdown_content = self._process_plantuml_blocks(markdown_content)

        # Pre-process OpenAPI blocks (convert to inline markdown) - always enabled
        markdown_content = self._process_openapi_blocks(markdown_content, base_path)

        # Pre-process tabs blocks
        markdown_content = self._process_tabs_blocks(markdown_content)

        # Remove skipped blocks
        markdown_content = self._process_skip_blocks(markdown_content)

        # Find local images
        images = self._find_local_images(markdown_content, base_path)

        # Convert to HTML first
        html_content = self.md.convert(markdown_content)

        # Post-process HTML to CSF
        csf_content = self._html_to_csf(html_content)

        return ConvertResult(
            csf_content=csf_content,
            title=title,
            images=images,
            attachments=[],
            mermaid_images=mermaid_images,
            drawio_attachments=drawio_attachments,
        )

    def parse_frontmatter(
        self,
        markdown_content: str,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Parse and separate YAML frontmatter from Markdown content.

        Args:
            markdown_content: Complete Markdown content with frontmatter

        Returns:
            Tuple of (frontmatter_dict, body_content)
        """
        post = frontmatter.loads(markdown_content)
        return dict(post.metadata), post.content

    def update_frontmatter(
        self,
        md_path: Path,
        updates: Dict[str, Any],
    ) -> None:
        """
        Update Markdown file's frontmatter with new values.

        Args:
            md_path: Path to the Markdown file
            updates: Dictionary of values to update
        """
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        post = frontmatter.loads(content)
        post.metadata.update(updates)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))

    def _extract_title(self, content: str) -> str:
        """Extract title from first H1 heading."""
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return "Untitled"

    def _remove_first_heading(self, content: str) -> str:
        """Remove the first H1 heading from content."""
        return re.sub(r'^#\s+.+\n*', '', content, count=1)

    def _process_admonitions(self, content: str) -> str:
        """
        Process GitHub-style admonitions to Confluence macros.

        Converts:
        > [!NOTE]
        > This is a note

        To a placeholder that will be converted to Confluence macro.
        """
        def replace_admonition(match):
            admon_type = match.group(1).upper()
            admon_content = match.group(2)
            # Clean up the content (remove leading > from each line)
            lines = admon_content.strip().split('\n')
            cleaned_lines = [re.sub(r'^>\s?', '', line) for line in lines]
            content = '\n'.join(cleaned_lines)

            macro_name = self.ADMONITION_MAP.get(admon_type, 'info')
            return f'<!-- ADMONITION:{macro_name} -->\n{content}\n<!-- /ADMONITION -->'

        # Match admonition blocks
        pattern = r'>\s*\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT)\]\s*\n((?:>.*\n?)*)'
        return re.sub(pattern, replace_admonition, content, flags=re.IGNORECASE)

    def _find_local_images(
        self,
        content: str,
        base_path: Optional[Path]
    ) -> List[Path]:
        """Find local image references in Markdown content."""
        images = []

        # Match markdown image syntax: ![alt](path)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        for match in re.finditer(pattern, content):
            img_path = match.group(2)

            # Skip URLs
            if img_path.startswith(('http://', 'https://', '//')):
                continue

            # Resolve relative path
            if base_path:
                full_path = base_path / img_path
                if full_path.exists():
                    images.append(full_path)

        return images

    def _html_to_csf(self, html_content: str) -> str:
        """
        Convert HTML to Confluence Storage Format.

        Uses a two-phase approach:
        1. Extract code blocks before BeautifulSoup processing (to preserve CDATA)
        2. Process other elements with BeautifulSoup
        3. Restore code blocks and admonitions with string replacement
        """
        # Phase 1: Extract code blocks before BeautifulSoup touches them
        code_blocks: List[Tuple[str, str]] = []

        def extract_code_block(match):
            full_match = match.group(0)
            # Parse the pre/code structure
            code_match = re.search(
                r'<code(?:\s+class="([^"]*)")?>(.*?)</code>',
                full_match,
                re.DOTALL
            )
            if code_match:
                classes = code_match.group(1) or ''
                code_text = code_match.group(2)

                # Extract language from class
                language = ''
                if classes:
                    for cls in classes.split():
                        if cls.startswith('language-'):
                            language = cls.replace('language-', '')
                            break

                # Unescape HTML entities in code
                code_text = (code_text
                    .replace('&lt;', '<')
                    .replace('&gt;', '>')
                    .replace('&amp;', '&')
                    .replace('&quot;', '"')
                )

                placeholder = f'__CODE_BLOCK_{len(code_blocks)}__'
                code_blocks.append((language, code_text))
                return placeholder
            return full_match

        # Extract all <pre><code>...</code></pre> blocks
        html_content = re.sub(
            r'<pre><code[^>]*>.*?</code></pre>',
            extract_code_block,
            html_content,
            flags=re.DOTALL
        )

        # Phase 2: Process with BeautifulSoup (only for images and tables)
        soup = BeautifulSoup(html_content, 'html.parser')

        # Process heading anchors
        if self.options.heading_anchors:
            self._process_heading_anchors(soup)

        # Process in-page anchor links
        self._process_anchor_links(soup)

        # Convert HTML details/summary to Confluence expand macro
        self._process_details_expand(soup)

        # Convert Markdown image syntax inside expand macros
        self._process_expand_markdown_images(soup)

        # Process images
        self._process_images(soup)

        # Process tables
        self._process_tables(soup)

        # Phase 3: Convert to string
        result = str(soup)

        # Restore code blocks (must be done on string to preserve CDATA)
        for idx, (language, code_text) in enumerate(code_blocks):
            placeholder = f'__CODE_BLOCK_{idx}__'

            if language == 'mermaid':
                mermaid_markdown = f"```mermaid\n{code_text.rstrip('\n')}\n```"
                macro = f'''<ac:structured-macro ac:name="markdown" ac:schema-version="1">
<ac:plain-text-body><![CDATA[{mermaid_markdown}]]></ac:plain-text-body>
</ac:structured-macro>'''
            else:
                # Build Confluence code macro
                lang_param = ''
                if language:
                    lang_param = f'<ac:parameter ac:name="language">{language}</ac:parameter>\n'

                macro = f'''<ac:structured-macro ac:name="code" ac:schema-version="1">
{lang_param}<ac:plain-text-body><![CDATA[{code_text}]]></ac:plain-text-body>
</ac:structured-macro>'''

            result = result.replace(placeholder, macro)

        # Process drawio placeholders (on string level)
        result = self._process_drawio_placeholders(result)

        # Process plantuml placeholders (on string level)
        result = self._process_plantuml_placeholders(result)

        # Process admonition placeholders (on string level)
        result = self._process_admonition_placeholders(result)

        return result

    def _process_admonition_placeholders(self, html_str: str) -> str:
        """Convert admonition placeholders to Confluence macros."""
        def replace_placeholder(match):
            macro_type = match.group(1)
            content = match.group(2).strip()

            return f'''<ac:structured-macro ac:name="{macro_type}" ac:schema-version="1">
<ac:rich-text-body>
<p>{content}</p>
</ac:rich-text-body>
</ac:structured-macro>'''

        pattern = r'<!-- ADMONITION:(\w+) -->\s*(.*?)\s*<!-- /ADMONITION -->'
        return re.sub(pattern, replace_placeholder, html_str, flags=re.DOTALL)

    def _process_drawio_placeholders(self, html_str: str) -> str:
        """Convert drawio placeholders to Confluence macros."""
        def replace_placeholder(match):
            payload = match.group(1).strip()
            try:
                params = json.loads(payload)
            except json.JSONDecodeError:
                params = {"name": payload}

            diagram_name = params.get("name", "").strip()
            lines = [
                '<ac:structured-macro ac:name="drawio" ac:schema-version="1">',
                f'<ac:parameter ac:name="border">{params.get("border", "true")}</ac:parameter>',
                f'<ac:parameter ac:name="diagramName">{diagram_name}</ac:parameter>',
                f'<ac:parameter ac:name="simpleViewer">{params.get("simpleViewer", "false")}</ac:parameter>',
                '<ac:parameter ac:name="width" />',
                f'<ac:parameter ac:name="links">{params.get("links", "auto")}</ac:parameter>',
                f'<ac:parameter ac:name="tbstyle">{params.get("tbstyle", "top")}</ac:parameter>',
                f'<ac:parameter ac:name="lbox">{params.get("lbox", "true")}</ac:parameter>',
            ]
            if params.get("page"):
                lines.append(f'<ac:parameter ac:name="page">{params["page"]}</ac:parameter>')
            if params.get("aspect"):
                lines.append(f'<ac:parameter ac:name="aspect">{params["aspect"]}</ac:parameter>')
            if params.get("aspectHash"):
                lines.append(f'<ac:parameter ac:name="aspectHash">{params["aspectHash"]}</ac:parameter>')
            if "diagramDisplayName" in params:
                lines.append(f'<ac:parameter ac:name="diagramDisplayName">{params.get("diagramDisplayName","")}</ac:parameter>')
            if params.get("diagramWidth"):
                lines.append(f'<ac:parameter ac:name="diagramWidth">{params["diagramWidth"]}</ac:parameter>')
            if params.get("height"):
                lines.append(f'<ac:parameter ac:name="height">{params["height"]}</ac:parameter>')
            lines.append('</ac:structured-macro>')
            return "\n".join(lines)

        pattern = r'<!--\s*DRAWIO:(.*?)\s*-->'
        return re.sub(pattern, replace_placeholder, html_str)

    def _process_images(self, soup) -> None:
        """Convert images to Confluence attachment references."""
        for img in soup.find_all('img'):
            src = img.get('src', '')
            alt_text = img.get('alt', '')

            # Skip external URLs - keep as is
            if src.startswith(('http://', 'https://')):
                continue

            # For local images, create Confluence image macro
            # Extract filename from path
            filename = Path(src).name

            ac_image = soup.new_tag('ac:image')
            if self.options.alignment:
                ac_image['ac:align'] = self.options.alignment
            if self.options.max_image_width:
                ac_image['ac:width'] = str(self.options.max_image_width)
            if alt_text:
                ac_image['ac:alt'] = alt_text

            attachment = soup.new_tag('ri:attachment')
            attachment['ri:filename'] = filename
            ac_image.append(attachment)

            img.replace_with(ac_image)

    def _process_details_expand(self, soup) -> None:
        """Convert <details><summary> to Confluence expand macro."""
        for details in soup.find_all('details'):
            summary = details.find('summary')
            title = summary.get_text(strip=True) if summary else 'Details'

            # Build expand macro
            macro = soup.new_tag('ac:structured-macro')
            macro['ac:name'] = 'expand'
            macro['ac:schema-version'] = '1'
            title_param = soup.new_tag('ac:parameter')
            title_param['ac:name'] = 'title'
            title_param.string = title
            macro.append(title_param)

            body = soup.new_tag('ac:rich-text-body')

            # Move all children except summary into body
            for child in list(details.children):
                if summary and child == summary:
                    continue
                if getattr(child, 'name', None) == 'summary':
                    continue
                body.append(child)

            macro.append(body)
            details.replace_with(macro)

    def _process_expand_markdown_images(self, soup) -> None:
        """Convert markdown image syntax inside expand macros to Confluence image macros."""
        for macro in soup.find_all('ac:structured-macro', attrs={'ac:name': 'expand'}):
            body = macro.find('ac:rich-text-body')
            if not body:
                continue
            raw = ''.join(str(x) for x in body.contents)
            if '![`' in raw:
                pass
            # Replace markdown images with Confluence image macros
            def repl(match):
                alt_text = match.group(1)
                src = match.group(2)
                filename = Path(src).name
                parts = [
                    '<ac:image',
                ]
                if self.options.alignment:
                    parts.append(f' ac:align="{self.options.alignment}"')
                if self.options.max_image_width:
                    parts.append(f' ac:width="{self.options.max_image_width}"')
                if alt_text:
                    parts.append(f' ac:alt="{alt_text}"')
                parts.append('>')
                parts.append(f'<ri:attachment ri:filename="{filename}" />')
                parts.append('</ac:image>')
                return ''.join(parts)

            replaced = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl, raw)
            if replaced != raw:
                body.clear()
                fragment = BeautifulSoup(replaced, 'html.parser')
                for child in list(fragment.contents):
                    body.append(child)

    def _process_heading_anchors(self, soup) -> None:
        """Insert Confluence anchor macros before headings."""
        for heading in soup.find_all(re.compile(r'^h[1-6]$')):
            text = heading.get_text(strip=True)
            if not text:
                continue
            anchor = self._slugify_heading(text)
            if not anchor:
                continue
            macro = soup.new_tag('ac:structured-macro')
            macro['ac:name'] = 'anchor'
            param = soup.new_tag('ac:parameter')
            param['ac:name'] = ''
            param.string = anchor
            macro.append(param)
            heading.insert_before(macro)

    def _process_anchor_links(self, soup) -> None:
        """Convert in-page links to Confluence anchor links."""
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if not href.startswith('#'):
                continue
            anchor = href[1:]
            if not anchor:
                continue
            ac_link = soup.new_tag('ac:link')
            ac_link['ac:anchor'] = anchor
            body = soup.new_tag('ac:plain-text-link-body')
            body.string = link.get_text()
            ac_link.append(body)
            link.replace_with(ac_link)

    def _process_tabs_blocks(self, content: str) -> str:
        """
        Convert markdown tab blocks into Confluence tab macros.

        Syntax:
        <!-- tabs:start -->
        ### Tab: Title
        content...
        ---
        ### Tab: Title2
        content...
        <!-- tabs:end -->
        """
        pattern = r'<!--\s*tabs:start\s*-->(.*?)<!--\s*tabs:end\s*-->'

        def replace_block(match):
            block = match.group(1).strip('\n')
            tab_pattern = re.compile(r'^\s*#{2,4}\s*Tab:\s*(.+?)\s*$',
                                     re.MULTILINE)
            matches = list(tab_pattern.finditer(block))
            if not matches:
                return match.group(0)

            tabs = []
            for idx, m in enumerate(matches):
                title = m.group(1).strip()
                start = m.end()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
                body = block[start:end].strip()
                body = re.sub(r'^\s*(---|\*\*\*)\s*$', '', body, flags=re.MULTILINE).strip()
                tabs.append((title, body))

            tab_pages = []
            for title, body in tabs:
                tab_html = markdown.markdown(body, extensions=self._md_extensions)
                tab_pages.append(
                    '<ac:structured-macro ac:name="tab-page" ac:schema-version="1">'
                    f'<ac:parameter ac:name="title">{title}</ac:parameter>'
                    f'<ac:rich-text-body>{tab_html}</ac:rich-text-body>'
                    '</ac:structured-macro>'
                )

            return (
                '<ac:structured-macro ac:name="tab-container" ac:schema-version="1">'
                '<ac:rich-text-body>'
                + ''.join(tab_pages) +
                '</ac:rich-text-body></ac:structured-macro>'
            )

        return re.sub(pattern, replace_block, content, flags=re.DOTALL)

    def _process_skip_blocks(self, content: str) -> str:
        """
        Remove blocks marked to skip upload.

        Syntax:
        <!-- cp-tools:skip-start -->
        ...content...
        <!-- cp-tools:skip-end -->
        """
        pattern = r'<!--\s*cp-tools:skip-start\s*-->.*?<!--\s*cp-tools:skip-end\s*-->'
        return re.sub(pattern, '', content, flags=re.DOTALL)

    def _process_openapi_blocks(
        self,
        content: str,
        base_path: Optional[Path],
    ) -> str:
        """
        Process OpenAPI code blocks and convert to inline Markdown.

        Syntax (recommended):
        ```openapi file=api/openapi.yaml
        ```
        or:
        ```openapi
        api/openapi.yaml
        ```

        Supported parameters:
        - file/path: Path to OpenAPI file (required)
        - title: Override the API title (optional)
        - include_toc: Include table of contents (default: true)
        - include_schemas: Include schema definitions (default: true)
        - group_by_tag: Group endpoints by tag (default: true)

        Args:
            content: Markdown content
            base_path: Base path for resolving relative file paths

        Returns:
            Modified content with OpenAPI blocks replaced by rendered Markdown
        """
        from .openapi_converter import OpenAPIConverter, ConvertOptions

        def parse_info(info: str) -> Dict[str, str]:
            args: Dict[str, str] = {}
            if not info:
                return args
            try:
                parts = shlex.split(info)
            except ValueError:
                parts = info.split()
            for token in parts:
                if '=' in token:
                    key, value = token.split('=', 1)
                    args[key.strip()] = value.strip()
            return args

        def resolve_path(raw_path: str) -> Path:
            if base_path:
                return (base_path / raw_path).resolve()
            return Path(raw_path).resolve()

        def replace_openapi_block(match) -> str:
            info = (match.group(1) or '').strip()
            body = (match.group(2) or '').strip()
            args = parse_info(info)

            # Parse body for key=value lines
            if body:
                for line in body.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        args[key.strip()] = value.strip()

            # Get file path
            raw_path = args.get('file') or args.get('path')
            if not raw_path:
                # If body is a single line without '=', treat it as file path
                if body and '\n' not in body and '=' not in body:
                    raw_path = body.strip()

            if not raw_path:
                print("  ⚠️ OpenAPI block missing file path; keeping original block")
                return match.group(0)

            file_path = resolve_path(raw_path)
            if not file_path.exists():
                print(f"  ⚠️ OpenAPI file not found: {file_path}; keeping original block")
                return match.group(0)

            # Parse options
            def str_to_bool(s: str) -> bool:
                return s.lower() in ('true', '1', 'yes')

            options = ConvertOptions(
                include_toc=str_to_bool(args.get('include_toc', 'true')),
                include_schemas=str_to_bool(args.get('include_schemas', 'true')),
                group_by_tag=str_to_bool(args.get('group_by_tag', 'true')),
                include_examples=str_to_bool(args.get('include_examples', 'true')),
            )

            try:
                converter = OpenAPIConverter(options)
                result = converter.convert_file(file_path)
                print(f"  📄 Rendered OpenAPI: {file_path.name} ({result.endpoints_count} endpoints)")

                # Build the rendered content
                rendered = result.markdown

                # Override title if specified
                if 'title' in args:
                    # Replace the first H1 heading with custom title
                    rendered = re.sub(
                        r'^# .+\n',
                        f"# {args['title']}\n",
                        rendered,
                        count=1
                    )

                return rendered

            except Exception as e:
                print(f"  ⚠️ Failed to convert OpenAPI {file_path.name}: {e}")
                return match.group(0)

        pattern = r'```openapi([^\n]*)\n(.*?)\n?```'
        modified_content = re.sub(
            pattern,
            replace_openapi_block,
            content,
            flags=re.DOTALL
        )

        return modified_content

    def _slugify_heading(self, text: str) -> str:
        """Create anchor name that matches common TOC generators."""
        slug = text.strip()
        # Remove dots in numeric prefixes like "4.1"
        slug = slug.replace('.', '')
        # Normalize whitespace to dashes
        slug = re.sub(r'\s+', '-', slug)
        # Remove punctuation except dash/underscore and CJK/alnum
        slug = re.sub(r'[^\w\u4e00-\u9fff\-]+', '', slug)
        slug = re.sub(r'-{2,}', '-', slug)
        return slug.strip('-')

    def _process_tables(self, soup) -> None:
        """Add Confluence table classes."""
        for table in soup.find_all('table'):
            table['class'] = table.get('class', []) + ['confluenceTable']

            for th in table.find_all('th'):
                th['class'] = th.get('class', []) + ['confluenceTh']

            for td in table.find_all('td'):
                td['class'] = td.get('class', []) + ['confluenceTd']

    def _process_mermaid_blocks(
        self,
        content: str,
    ) -> Tuple[str, List[Path]]:
        """
        Process Mermaid code blocks and render them to images.

        Finds all ```mermaid code blocks, renders them to PNG images,
        and replaces the code blocks with image references.

        Args:
            content: Markdown content

        Returns:
            Tuple of (modified content, list of rendered image paths)
        """
        if not self._mermaid_renderer:
            return content, []

        # Check if mmdc is available
        if not self._mermaid_renderer.is_available():
            print("  ⚠️ mermaid-cli (mmdc) not found, Mermaid blocks will be preserved for Confluence markdown rendering")
            return content, []

        rendered_images: List[Path] = []
        mermaid_count = 0

        def replace_mermaid_block(match) -> str:
            nonlocal mermaid_count
            mermaid_code = match.group(1).strip()
            mermaid_count += 1

            # Render the diagram
            result = self._mermaid_renderer.render(mermaid_code)

            if result.success and result.image_path:
                rendered_images.append(result.image_path)
                filename = result.image_path.name
                print(
                    "  🎨 Rendered Mermaid diagram "
                    f"#{mermaid_count}: {filename} -> {result.image_path.resolve()}"
                )
                # Return markdown image reference
                return f"![Mermaid Diagram {mermaid_count}]({filename})"
            else:
                print(f"  ⚠️ Failed to render Mermaid #{mermaid_count}: {result.error}")
                # Keep original block so Confluence can still render Mermaid natively
                return match.group(0)

        # Match ```mermaid ... ``` blocks
        pattern = r'```mermaid\s*\n(.*?)\n```'
        modified_content = re.sub(
            pattern,
            replace_mermaid_block,
            content,
            flags=re.DOTALL
        )

        return modified_content, rendered_images

    def _process_plantuml_blocks(
        self,
        content: str,
    ) -> str:
        """
        Process PlantUML code blocks and convert to Confluence macro placeholders.

        Finds all ```plantuml code blocks and replaces them with placeholders
        that will be converted to Confluence PlantUML macros.

        Args:
            content: Markdown content

        Returns:
            Modified content with PlantUML placeholders
        """
        # Check if there are any plantuml blocks
        if '```plantuml' not in content:
            return content

        plantuml_count = 0

        def replace_plantuml_block(match) -> str:
            nonlocal plantuml_count
            plantuml_code = match.group(1).strip()
            plantuml_count += 1

            print(f"  🌱 Found PlantUML diagram #{plantuml_count}")

            # Use base64 encoding to avoid issues with special characters like -->
            import base64
            encoded_code = base64.b64encode(plantuml_code.encode('utf-8')).decode('ascii')

            # Return placeholder that will be converted to Confluence macro
            return f'<!-- PLANTUML_BASE64:{encoded_code} -->'

        # Match ```plantuml ... ``` blocks
        pattern = r'```plantuml\s*\n(.*?)\n```'
        modified_content = re.sub(
            pattern,
            replace_plantuml_block,
            content,
            flags=re.DOTALL
        )

        return modified_content

    def _process_plantuml_placeholders(self, html_str: str) -> str:
        """Convert PlantUML placeholders to Confluence PlantUML macros."""
        import base64

        def replace_placeholder(match):
            encoded_code = match.group(1).strip()
            try:
                plantuml_code = base64.b64decode(encoded_code).decode('utf-8')
            except Exception:
                # Fallback: treat as raw code
                plantuml_code = encoded_code

            # Build Confluence PlantUML macro
            # The macro name may vary depending on the plugin installed
            # Common names: "plantuml", "plantuml-macro", "plantumlrender"
            macro = f'''<ac:structured-macro ac:name="plantuml" ac:schema-version="1">
<ac:plain-text-body><![CDATA[{plantuml_code}]]></ac:plain-text-body>
</ac:structured-macro>'''
            return macro

        pattern = r'<!--\s*PLANTUML_BASE64:([A-Za-z0-9+/=]+)\s*-->'
        return re.sub(pattern, replace_placeholder, html_str)

    def _process_drawio_blocks(
        self,
        content: str,
        base_path: Optional[Path],
    ) -> Tuple[str, List[Tuple[Path, str]]]:
        """
        Process Draw.io code blocks into Confluence macros.

        Syntax (recommended):
        ```drawio name=diagram file=diagrams/arch.drawio
        ```
        or:
        ```drawio
        diagrams/arch.drawio
        ```
        """
        attachments: List[Tuple[Path, str]] = []

        def parse_info(info: str) -> Dict[str, str]:
            args: Dict[str, str] = {}
            if not info:
                return args
            try:
                parts = shlex.split(info)
            except ValueError:
                parts = info.split()
            for token in parts:
                if '=' in token:
                    key, value = token.split('=', 1)
                    args[key.strip()] = value.strip()
            return args

        def resolve_path(raw_path: str) -> Path:
            if base_path:
                return (base_path / raw_path).resolve()
            return Path(raw_path).resolve()

        def parse_body_kv_lines(text: str) -> Dict[str, str]:
            kv: Dict[str, str] = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    kv[key.strip()] = value.strip()
            return kv

        def replace_drawio_block(match) -> str:
            info = (match.group(1) or '').strip()
            body = (match.group(2) or '').strip()
            args = parse_info(info)
            if body:
                args.update(parse_body_kv_lines(body))

            raw_path = args.get('file') or args.get('path')
            if not raw_path:
                if body and '\n' not in body and not body.lstrip().startswith('<'):
                    raw_path = body.strip()

            if not raw_path:
                print("  ⚠️ Draw.io block missing file path; keeping original block")
                return match.group(0)

            file_path = resolve_path(raw_path)
            if not file_path.exists():
                print(f"  ⚠️ Draw.io file not found: {file_path}; keeping original block")
                return match.group(0)

            diagram_name = args.get('name') or file_path.stem
            filename = diagram_name
            attachments.append((file_path, diagram_name, filename))

            drawio_params = {
                "name": diagram_name,
                "border": args.get("border", "true"),
                "simpleViewer": args.get("simpleViewer", "false"),
                "links": args.get("links", "auto"),
                "tbstyle": args.get("tbstyle", "top"),
                "lbox": args.get("lbox", "true"),
                "width": args.get("width", ""),
            }
            if "page" in args:
                drawio_params["page"] = args["page"]
                page_info = self._get_drawio_page_info(file_path, args["page"])
                if page_info:
                    drawio_params["aspect"] = page_info["id"]
                    drawio_params["aspectHash"] = hashlib.sha1(
                        page_info["id"].encode()
                    ).hexdigest()
            if "diagramWidth" in args:
                drawio_params["diagramWidth"] = args["diagramWidth"]
            if "height" in args:
                drawio_params["height"] = args["height"]

            return f"<!-- DRAWIO:{json.dumps(drawio_params, ensure_ascii=False)} -->"

        pattern = r'```drawio([^\n]*)\n(.*?)```'
        modified_content = re.sub(
            pattern,
            replace_drawio_block,
            content,
            flags=re.DOTALL
        )

        return modified_content, attachments

    def _get_drawio_page_info(
        self,
        file_path: Path,
        page_value: str,
    ) -> Optional[Dict[str, str]]:
        """Get drawio page info by index (0-based) or by name."""
        try:
            index = int(page_value)
        except ValueError:
            index = None

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            diagrams = root.findall('diagram')
            if index is not None:
                if 0 <= index < len(diagrams):
                    diagram = diagrams[index]
                    return {
                        "id": diagram.get("id", ""),
                        "name": diagram.get("name", ""),
                    }
                print(f"  ⚠️ Draw.io page index out of range: {page_value}")
                return None
            # Fallback: find by name
            for diagram in diagrams:
                if diagram.get("name") == page_value:
                    return {
                        "id": diagram.get("id", ""),
                        "name": diagram.get("name", ""),
                    }
        except Exception as e:
            print(f"  ⚠️ Failed to parse drawio file: {file_path} ({e})")
        return None
