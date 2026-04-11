"""
Simple Jinja2 demonstration without requiring jinja2 library
Generates HTML directly to show the integration pattern
"""

import json
from pathlib import Path

from tree_timeline_python_example import create_trace_node


def render_with_template_string(trace_data, title='Trace Timeline', metadata=None):
    """
    Render trace using template string (no jinja2 library needed)
    This demonstrates the pattern that would be used with Jinja2
    """
    metadata = metadata or {}
    
    # Template string (similar to Jinja2 template)
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="tree-timeline-renderer.css">
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
        .metadata {{
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        .metadata-item {{
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid #f1f3f5;
        }}
        .metadata-item:last-child {{
            border-bottom: none;
        }}
        .metadata-label {{
            font-weight: 600;
            color: #495057;
        }}
        .metadata-value {{
            color: #6c757d;
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

        {metadata_html}

        <div class="controls">
            <button class="btn" onclick="renderer.expandAll()">Expand All</button>
            <button class="btn" onclick="renderer.collapseAll()">Collapse All</button>
        </div>

        <div id="timeline-container"></div>
    </div>

    <script src="tree-timeline-renderer.js"></script>
    <script>
        const traceData = {trace_data_json};
        
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
    
    # Build metadata HTML
    metadata_html = ''
    if metadata:
        items_html = '\n'.join([
            f'<div class="metadata-item"><span class="metadata-label">{key}</span><span class="metadata-value">{value}</span></div>'
            for key, value in metadata.items()
        ])
        metadata_html = f'<div class="metadata">{items_html}</div>'
    
    # Fill template
    html = html_template.format(
        title=title,
        metadata_html=metadata_html,
        trace_data_json=json.dumps(trace_data, indent=2)
    )
    
    return html


if __name__ == '__main__':
    # Create sample trace
    trace_data = create_trace_node(
        'trace-1', 'User Login Flow', 'TRACE', 0, 3500,
        children=[
            create_trace_node('span-1', 'Validate Credentials', 'SPAN', 0, 1200, children=[
                create_trace_node('span-1-1', 'Hash Password', 'SPAN', 10, 500),
                create_trace_node('span-1-2', 'Query Database', 'SPAN', 520, 1180)
            ]),
            create_trace_node('span-2', 'Create Session', 'SPAN', 1250, 2100, children=[
                create_trace_node('gen-2-1', 'Generate Token', 'GENERATION', 1260, 2080)
            ]),
            create_trace_node('span-3', 'Update User Profile', 'SPAN', 2150, 3450, children=[
                create_trace_node('span-3-1', 'Fetch User Data', 'SPAN', 2160, 2800),
                create_trace_node('span-3-2', 'Update Last Login', 'SPAN', 2850, 3420)
            ])
        ]
    )
    
    # Render HTML
    html = render_with_template_string(
        trace_data,
        title='User Login Flow Trace',
        metadata={
            'User ID': 'user_12345',
            'Timestamp': '2026-01-11 01:30:00',
            'Duration': '3.5s',
            'Status': 'Success'
        }
    )
    
    # Save to file
    output_path = 'login_trace_demo.html'
    Path(output_path).write_text(html, encoding='utf-8')
    print(f"✅ Generated: {output_path}")
    print("\n这个示例展示了Jinja2集成的模式:")
    print("1. 使用模板字符串(类似Jinja2模板)")
    print("2. 传入trace数据和元数据")
    print("3. 生成完整的HTML文件")
    print("\n在实际使用中,将模板字符串替换为Jinja2模板文件即可。")
