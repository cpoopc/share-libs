"""
Tree-Timeline Renderer - Python Integration Example

This example shows how to use the tree-timeline renderer from Python
by generating HTML with embedded trace data.
"""

import json
from pathlib import Path
from typing import Any, Dict, List


class TreeTimelineRenderer:
    """Python wrapper for the tree-timeline JavaScript renderer"""
    
    def __init__(self, css_path: str = "tree-timeline-renderer.css", 
                 js_path: str = "tree-timeline-renderer.js"):
        """
        Initialize the renderer
        
        Args:
            css_path: Path to CSS file
            js_path: Path to JavaScript file
        """
        self.css_path = css_path
        self.js_path = js_path
    
    def render_to_html(self, trace_data: Dict[str, Any], 
                      output_path: str = "timeline.html",
                      title: str = "Trace Timeline") -> str:
        """
        Render trace data to an HTML file
        
        Args:
            trace_data: Hierarchical trace data dictionary
            output_path: Output HTML file path
            title: Page title
            
        Returns:
            Path to generated HTML file
        """
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="{self.css_path}">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f8f9fa;
            padding: 2rem;
            margin: 0;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 2rem;
        }}
        .header h1 {{
            font-size: 2rem;
            color: #212529;
            margin-bottom: 0.5rem;
        }}
        .controls {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            justify-content: center;
        }}
        .btn {{
            padding: 0.5rem 1rem;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            background: white;
            cursor: pointer;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div class="controls">
            <button class="btn" onclick="renderer.expandAll()">Expand All</button>
            <button class="btn" onclick="renderer.collapseAll()">Collapse All</button>
        </div>
        <div id="timeline-container"></div>
    </div>
    
    <script src="{self.js_path}"></script>
    <script>
        const traceData = {json.dumps(trace_data, indent=2)};
        
        const renderer = new TreeTimelineRenderer({{
            container: '#timeline-container',
            onNodeClick: (node) => {{
                console.log('Node clicked:', node);
            }}
        }});
        
        renderer.render(traceData);
    </script>
</body>
</html>"""
        
        # Write to file
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path
    
    def render_inline(self, trace_data: Dict[str, Any]) -> str:
        """
        Render trace data to inline HTML (for Jupyter notebooks)
        
        Args:
            trace_data: Hierarchical trace data dictionary
            
        Returns:
            HTML string with inline CSS and JS
        """
        # Read CSS and JS files
        css_content = Path(self.css_path).read_text(encoding='utf-8')
        js_content = Path(self.js_path).read_text(encoding='utf-8')
        
        html = f"""
<div id="timeline-inline-{id(trace_data)}">
    <style>{css_content}</style>
    <div class="controls">
        <button class="btn" onclick="renderer_{id(trace_data)}.expandAll()">Expand All</button>
        <button class="btn" onclick="renderer_{id(trace_data)}.collapseAll()">Collapse All</button>
    </div>
    <div id="container-{id(trace_data)}"></div>
</div>
<script>
{js_content}

const traceData_{id(trace_data)} = {json.dumps(trace_data)};
const renderer_{id(trace_data)} = new TreeTimelineRenderer({{
    container: '#container-{id(trace_data)}',
    onNodeClick: (node) => console.log('Node clicked:', node)
}});
renderer_{id(trace_data)}.render(traceData_{id(trace_data)});
</script>
"""
        return html


def create_trace_node(node_id: str, name: str, node_type: str,
                     start_ms: float, end_ms: float,
                     children: List[Dict] = None) -> Dict[str, Any]:
    """
    Helper function to create a trace node
    
    Args:
        node_id: Unique node identifier
        name: Node name
        node_type: Node type (TRACE, SPAN, GENERATION, EVENT)
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
        children: List of child nodes
        
    Returns:
        Trace node dictionary
    """
    return {
        'id': node_id,
        'name': name,
        'type': node_type,
        'start_ms': start_ms,
        'end_ms': end_ms,
        'children': children or []
    }


# Example usage
if __name__ == '__main__':
    # Create sample trace data
    trace_data = create_trace_node(
        'trace-1', 'API Request', 'TRACE', 0, 5500,
        children=[
            create_trace_node(
                'span-1', 'Authentication', 'SPAN', 0, 880,
                children=[
                    create_trace_node('span-1-1', 'Validate Token', 'SPAN', 2, 880, children=[
                        create_trace_node('span-1-1-1', 'Parse JWT', 'SPAN', 5, 8),
                        create_trace_node('gen-1-1-2', 'Check Signature', 'GENERATION', 10, 870)
                    ])
                ]
            ),
            create_trace_node(
                'span-2', 'Database Query', 'SPAN', 900, 3500,
                children=[
                    create_trace_node('span-2-1', 'Connect', 'SPAN', 904, 920),
                    create_trace_node('gen-2-2', 'Execute Query', 'GENERATION', 925, 3480)
                ]
            ),
            create_trace_node(
                'span-3', 'Response Generation', 'SPAN', 3600, 5500,
                children=[
                    create_trace_node('span-3-1', 'Format Data', 'SPAN', 3610, 3800),
                    create_trace_node('gen-3-2', 'Serialize JSON', 'GENERATION', 3850, 5450)
                ]
            )
        ]
    )
    
    # Method 1: Render to HTML file
    renderer = TreeTimelineRenderer()
    output_file = renderer.render_to_html(
        trace_data,
        output_path='example_trace.html',
        title='API Request Trace'
    )
    print(f"Generated: {output_file}")
    
    # Method 2: For Jupyter notebooks
    # from IPython.display import HTML
    # html_content = renderer.render_inline(trace_data)
    # display(HTML(html_content))
