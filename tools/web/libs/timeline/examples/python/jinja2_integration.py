"""
Tree-Timeline Renderer - Jinja2 Integration Example

This example demonstrates how to use the tree-timeline renderer with Jinja2 templates.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from tree_timeline_python_example import create_trace_node


def render_trace_with_jinja2(trace_data, output_path='trace_jinja2.html', **kwargs):
    """
    Render trace using Jinja2 template
    
    Args:
        trace_data: Hierarchical trace data
        output_path: Output HTML file path
        **kwargs: Additional template variables (title, description, metadata, etc.)
    
    Returns:
        Path to generated HTML file
    """
    # Setup Jinja2 environment
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('tree-timeline-template.j2')
    
    # Default values
    context = {
        'title': kwargs.get('title', 'Trace Timeline'),
        'description': kwargs.get('description', ''),
        'metadata': kwargs.get('metadata', {}),
        'trace_data': trace_data,
        'on_node_click_callback': kwargs.get('on_node_click_callback', '')
    }
    
    # Render template
    html = template.render(**context)
    
    # Write to file
    Path(output_path).write_text(html, encoding='utf-8')
    return output_path


# Example 1: Basic usage
def example_basic():
    """Basic Jinja2 integration example"""
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
    
    output = render_trace_with_jinja2(
        trace_data,
        output_path='login_trace_jinja2.html',
        title='User Login Flow Trace',
        description='Detailed trace of user authentication and session creation',
        metadata={
            'User ID': 'user_12345',
            'Timestamp': '2026-01-11 01:30:00',
            'Duration': '3.5s',
            'Status': 'Success'
        }
    )
    print(f"Generated: {output}")


# Example 2: With custom callback
def example_with_callback():
    """Example with custom JavaScript callback"""
    trace_data = create_trace_node(
        'trace-2', 'API Request', 'TRACE', 0, 2500,
        children=[
            create_trace_node('span-1', 'Parse Request', 'SPAN', 0, 300),
            create_trace_node('gen-1', 'Process Data', 'GENERATION', 350, 2200),
            create_trace_node('span-2', 'Send Response', 'SPAN', 2250, 2480)
        ]
    )
    
    # Custom JavaScript callback
    callback = """
        // Custom logic when node is clicked
        alert(`Clicked: ${node.name} (${node.type})`);
    """
    
    output = render_trace_with_jinja2(
        trace_data,
        output_path='api_trace_jinja2.html',
        title='API Request Trace',
        metadata={
            'Endpoint': '/api/v1/users',
            'Method': 'POST',
            'Status Code': '200'
        },
        on_node_click_callback=callback
    )
    print(f"Generated: {output}")


# Example 3: Integration with Flask
def example_flask_integration():
    """Example Flask application using Jinja2"""
    from flask import Flask, render_template
    
    app = Flask(__name__, template_folder='.')
    
    @app.route('/trace/<trace_id>')
    def show_trace(trace_id):
        # Fetch trace data (example)
        trace_data = create_trace_node(
            f'trace-{trace_id}', f'Trace {trace_id}', 'TRACE', 0, 5000,
            children=[
                create_trace_node('span-1', 'Step 1', 'SPAN', 0, 2000),
                create_trace_node('span-2', 'Step 2', 'SPAN', 2100, 4800)
            ]
        )
        
        return render_template(
            'tree-timeline-template.j2',
            title=f'Trace {trace_id}',
            description=f'Detailed view of trace {trace_id}',
            metadata={
                'Trace ID': trace_id,
                'Duration': '5.0s'
            },
            trace_data=trace_data
        )
    
    # Uncomment to run Flask app
    # app.run(debug=True)
    print("Flask integration example (commented out)")


# Example 4: Batch processing
def example_batch_processing():
    """Generate multiple trace HTML files from a list"""
    traces = [
        {
            'id': 'trace-001',
            'name': 'Database Query',
            'data': create_trace_node('t1', 'DB Query', 'TRACE', 0, 1500, children=[
                create_trace_node('s1', 'Connect', 'SPAN', 0, 200),
                create_trace_node('s2', 'Execute', 'SPAN', 210, 1480)
            ])
        },
        {
            'id': 'trace-002',
            'name': 'Cache Lookup',
            'data': create_trace_node('t2', 'Cache', 'TRACE', 0, 50, children=[
                create_trace_node('s1', 'Check Key', 'SPAN', 0, 45)
            ])
        }
    ]
    
    for trace in traces:
        output = render_trace_with_jinja2(
            trace['data'],
            output_path=f"{trace['id']}_jinja2.html",
            title=trace['name'],
            metadata={'Trace ID': trace['id']}
        )
        print(f"Generated: {output}")


if __name__ == '__main__':
    print("=== Jinja2 Integration Examples ===\n")
    
    print("1. Basic usage:")
    example_basic()
    
    print("\n2. With custom callback:")
    example_with_callback()
    
    print("\n3. Flask integration:")
    example_flask_integration()
    
    print("\n4. Batch processing:")
    example_batch_processing()
    
    print("\n✅ All examples completed!")
