#!/usr/bin/env python3
"""
OpenAPI to Markdown Converter

Converts OpenAPI 3.x specification files (YAML/JSON) to Markdown format
suitable for uploading to Confluence.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class ConvertOptions:
    """Conversion options for OpenAPI to Markdown."""
    include_examples: bool = True
    include_schemas: bool = True
    include_toc: bool = True
    group_by_tag: bool = True
    max_schema_depth: int = 3


@dataclass
class ConvertResult:
    """Result of OpenAPI to Markdown conversion."""
    markdown: str
    title: str
    version: str
    description: str
    endpoints_count: int


class OpenAPIConverter:
    """
    Converts OpenAPI 3.x specifications to Markdown.
    
    Supports:
    - OpenAPI 3.0.x and 3.1.x
    - YAML and JSON formats
    - Endpoints with parameters, request bodies, responses
    - Schema definitions with examples
    """

    HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    
    def __init__(self, options: Optional[ConvertOptions] = None):
        """Initialize the converter."""
        self.options = options or ConvertOptions()

    def convert_file(self, file_path: Path) -> ConvertResult:
        """
        Convert an OpenAPI file to Markdown.
        
        Args:
            file_path: Path to OpenAPI YAML/JSON file
            
        Returns:
            ConvertResult with markdown content and metadata
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"OpenAPI file not found: {file_path}")
        
        content = file_path.read_text(encoding='utf-8')
        
        # Parse based on file extension
        if file_path.suffix in ('.yaml', '.yml'):
            spec = yaml.safe_load(content)
        else:
            spec = json.loads(content)
        
        return self.convert(spec)

    def convert(self, spec: Dict[str, Any]) -> ConvertResult:
        """
        Convert an OpenAPI specification dict to Markdown.
        
        Args:
            spec: Parsed OpenAPI specification
            
        Returns:
            ConvertResult with markdown content and metadata
        """
        # Extract info
        info = spec.get('info', {})
        title = info.get('title', 'API Documentation')
        version = info.get('version', '1.0.0')
        description = info.get('description', '')
        
        # Build markdown sections
        sections = []
        
        # Title and description
        sections.append(f"# {title}\n")
        sections.append(f"**Version:** {version}\n")
        if description:
            sections.append(f"\n{description}\n")
        
        # Servers
        servers = spec.get('servers', [])
        if servers:
            sections.append(self._render_servers(servers))
        
        # Table of contents
        paths = spec.get('paths', {})
        if self.options.include_toc and paths:
            sections.append(self._render_toc(paths))
        
        # Endpoints
        endpoints_count = 0
        if self.options.group_by_tag:
            sections.append(self._render_endpoints_by_tag(paths, spec))
            endpoints_count = self._count_endpoints(paths)
        else:
            sections.append(self._render_endpoints(paths, spec))
            endpoints_count = self._count_endpoints(paths)
        
        # Schemas
        if self.options.include_schemas:
            components = spec.get('components', {})
            schemas = components.get('schemas', {})
            if schemas:
                sections.append(self._render_schemas(schemas))
        
        markdown = '\n'.join(sections)
        
        return ConvertResult(
            markdown=markdown,
            title=title,
            version=version,
            description=description,
            endpoints_count=endpoints_count,
        )

    def _render_servers(self, servers: List[Dict]) -> str:
        """Render servers section."""
        lines = ["\n## Servers\n"]
        for server in servers:
            url = server.get('url', '')
            desc = server.get('description', '')
            lines.append(f"- `{url}`" + (f" - {desc}" if desc else ""))
        return '\n'.join(lines) + '\n'

    def _render_toc(self, paths: Dict) -> str:
        """Render table of contents."""
        lines = ["\n## Table of Contents\n"]
        for path, methods in paths.items():
            for method in self.HTTP_METHODS:
                if method in methods:
                    op = methods[method]
                    summary = op.get('summary', f"{method.upper()} {path}")
                    anchor = self._slugify(f"{method}-{path}")
                    lines.append(f"- [{method.upper()} {path}](#{anchor}) - {summary}")
        return '\n'.join(lines) + '\n'

    def _count_endpoints(self, paths: Dict) -> int:
        """Count total number of endpoints."""
        count = 0
        for methods in paths.values():
            for method in self.HTTP_METHODS:
                if method in methods:
                    count += 1
        return count

    def _render_endpoints_by_tag(self, paths: Dict, spec: Dict) -> str:
        """Render endpoints grouped by tag."""
        # Group endpoints by tag
        tagged: Dict[str, List[Tuple[str, str, Dict]]] = {}
        untagged: List[Tuple[str, str, Dict]] = []

        for path, methods in paths.items():
            for method in self.HTTP_METHODS:
                if method in methods:
                    op = methods[method]
                    tags = op.get('tags', [])
                    if tags:
                        for tag in tags:
                            if tag not in tagged:
                                tagged[tag] = []
                            tagged[tag].append((path, method, op))
                    else:
                        untagged.append((path, method, op))

        lines = ["\n## Endpoints\n"]

        # Render tagged endpoints
        for tag, endpoints in sorted(tagged.items()):
            lines.append(f"\n### {tag}\n")
            for path, method, op in endpoints:
                lines.append(self._render_endpoint(path, method, op, spec))

        # Render untagged endpoints
        if untagged:
            lines.append("\n### Other\n")
            for path, method, op in untagged:
                lines.append(self._render_endpoint(path, method, op, spec))

        return '\n'.join(lines)

    def _render_endpoints(self, paths: Dict, spec: Dict) -> str:
        """Render endpoints without grouping."""
        lines = ["\n## Endpoints\n"]
        for path, methods in paths.items():
            for method in self.HTTP_METHODS:
                if method in methods:
                    lines.append(self._render_endpoint(path, method, methods[method], spec))
        return '\n'.join(lines)

    def _render_endpoint(self, path: str, method: str, op: Dict, spec: Dict) -> str:
        """Render a single endpoint."""
        lines = []

        # Header
        summary = op.get('summary', '')
        anchor = self._slugify(f"{method}-{path}")
        lines.append(f"\n#### {method.upper()} `{path}` {{#{anchor}}}\n")

        if summary:
            lines.append(f"**{summary}**\n")

        description = op.get('description', '')
        if description:
            lines.append(f"{description}\n")

        # Parameters
        params = op.get('parameters', [])
        if params:
            lines.append(self._render_parameters(params, spec))

        # Request body
        request_body = op.get('requestBody', {})
        if request_body:
            lines.append(self._render_request_body(request_body, spec))

        # Responses
        responses = op.get('responses', {})
        if responses:
            lines.append(self._render_responses(responses, spec))

        return '\n'.join(lines)

    def _render_parameters(self, params: List[Dict], spec: Dict) -> str:
        """Render parameters table."""
        lines = ["\n**Parameters:**\n"]
        lines.append("| Name | In | Type | Required | Description |")
        lines.append("|------|-----|------|----------|-------------|")

        for param in params:
            # Resolve $ref if present
            if '$ref' in param:
                param = self._resolve_ref(param['$ref'], spec)

            name = param.get('name', '')
            location = param.get('in', '')
            schema = param.get('schema', {})
            param_type = schema.get('type', 'string')
            required = '✓' if param.get('required', False) else ''
            desc = param.get('description', '').replace('\n', ' ')

            lines.append(f"| `{name}` | {location} | {param_type} | {required} | {desc} |")

        return '\n'.join(lines) + '\n'

    def _render_request_body(self, body: Dict, spec: Dict) -> str:
        """Render request body section."""
        lines = ["\n**Request Body:**\n"]

        content = body.get('content', {})
        for media_type, media_obj in content.items():
            lines.append(f"\nContent-Type: `{media_type}`\n")

            schema = media_obj.get('schema', {})
            if schema:
                lines.append(self._render_schema_block(schema, spec))

            # Example
            if self.options.include_examples:
                example = media_obj.get('example')
                if example:
                    lines.append("\n**Example:**\n")
                    lines.append(f"```json\n{json.dumps(example, indent=2)}\n```\n")

        return '\n'.join(lines)

    def _render_responses(self, responses: Dict, spec: Dict) -> str:
        """Render responses section."""
        lines = ["\n**Responses:**\n"]

        for status, response in responses.items():
            # Resolve $ref if present
            if '$ref' in response:
                response = self._resolve_ref(response['$ref'], spec)

            desc = response.get('description', '')
            lines.append(f"\n- **{status}**: {desc}")

            content = response.get('content', {})
            for media_type, media_obj in content.items():
                schema = media_obj.get('schema', {})
                if schema:
                    lines.append(f"\n  Content-Type: `{media_type}`\n")
                    lines.append(self._render_schema_block(schema, spec, indent=2))

        return '\n'.join(lines) + '\n'

    def _render_schema_block(self, schema: Dict, spec: Dict, indent: int = 0) -> str:
        """Render a schema as a code block."""
        # Resolve $ref if present
        if '$ref' in schema:
            ref_name = schema['$ref'].split('/')[-1]
            schema = self._resolve_ref(schema['$ref'], spec)
            schema_str = f"// Reference: {ref_name}\n"
        else:
            schema_str = ""

        # Simplify schema for display
        display_schema = self._simplify_schema(schema, spec, depth=0)
        schema_str += json.dumps(display_schema, indent=2)

        prefix = ""  # Do not indent code blocks - breaks markdown parsing
        lines = [f"{prefix}```json", schema_str, f"{prefix}```"]
        return '\n'.join(lines)

    def _simplify_schema(self, schema: Dict, spec: Dict, depth: int) -> Dict:
        """Simplify schema for display, resolving refs up to max depth."""
        if depth > self.options.max_schema_depth:
            return {"...": "max depth reached"}

        if '$ref' in schema:
            resolved = self._resolve_ref(schema['$ref'], spec)
            return self._simplify_schema(resolved, spec, depth + 1)

        result = {}

        if 'type' in schema:
            result['type'] = schema['type']

        if 'properties' in schema:
            result['properties'] = {}
            for prop_name, prop_schema in schema['properties'].items():
                result['properties'][prop_name] = self._simplify_schema(prop_schema, spec, depth + 1)

        if 'items' in schema:
            result['items'] = self._simplify_schema(schema['items'], spec, depth + 1)

        if 'required' in schema:
            result['required'] = schema['required']

        if 'enum' in schema:
            result['enum'] = schema['enum']

        if 'description' in schema:
            result['description'] = schema['description']

        return result if result else schema

    def _render_schemas(self, schemas: Dict) -> str:
        """Render component schemas section."""
        lines = ["\n## Schemas\n"]

        for name, schema in schemas.items():
            lines.append(f"\n### {name}\n")

            desc = schema.get('description', '')
            if desc:
                lines.append(f"{desc}\n")

            lines.append(f"```json\n{json.dumps(schema, indent=2)}\n```\n")

        return '\n'.join(lines)

    def _resolve_ref(self, ref: str, spec: Dict) -> Dict:
        """Resolve a $ref pointer."""
        if not ref.startswith('#/'):
            return {}

        parts = ref[2:].split('/')
        current = spec
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}
        return current if isinstance(current, dict) else {}

    def _slugify(self, text: str) -> str:
        """Create URL-safe anchor from text."""
        slug = text.lower()
        slug = re.sub(r'[{}]', '', slug)
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug


def convert_openapi_to_markdown(
    file_path: Path,
    options: Optional[ConvertOptions] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Convenience function to convert OpenAPI file to Markdown.

    Args:
        file_path: Path to OpenAPI file
        options: Conversion options

    Returns:
        Tuple of (markdown_content, metadata_dict)
    """
    converter = OpenAPIConverter(options)
    result = converter.convert_file(file_path)

    metadata = {
        'title': result.title,
        'version': result.version,
        'description': result.description,
        'endpoints_count': result.endpoints_count,
    }

    return result.markdown, metadata

