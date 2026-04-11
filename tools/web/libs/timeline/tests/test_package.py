"""
Test script for cptools-web package
"""

import sys
from pathlib import Path

# Add package to path for testing without installation
package_path = Path(__file__).parent.parent
sys.path.insert(0, str(package_path))

from cptools_web import TimelineRenderer, TreeTimelineRenderer, create_trace_node


def test_tree_timeline():
    """Test TreeTimelineRenderer"""
    print("Testing TreeTimelineRenderer...")
    
    # Create sample trace data
    trace = create_trace_node(
        'trace-1', 'Test API Request', 'TRACE', 0, 5000,
        children=[
            create_trace_node('span-1', 'Authentication', 'SPAN', 0, 1200),
            create_trace_node('span-2', 'Database Query', 'SPAN', 1300, 3500),
            create_trace_node('span-3', 'Response Generation', 'SPAN', 3600, 4900)
        ]
    )
    
    # Test renderer initialization
    renderer = TreeTimelineRenderer()
    print("✓ TreeTimelineRenderer initialized")
    
    # Test resource access methods
    css_content = renderer.get_css_content()
    assert len(css_content) > 0, "CSS content should not be empty"
    print(f"✓ CSS content loaded ({len(css_content)} bytes)")
    
    js_content = renderer.get_js_content()
    assert len(js_content) > 0, "JS content should not be empty"
    print(f"✓ JS content loaded ({len(js_content)} bytes)")
    
    # Test HTML generation
    output_path = '/tmp/test_tree_timeline.html'
    renderer.render_to_html(
        trace,
        output_path=output_path,
        title='Test Trace',
        metadata={'test': 'value'}
    )
    assert Path(output_path).exists(), "HTML file should be created"
    print(f"✓ HTML file generated: {output_path}")
    
    # Test inline rendering
    inline_html = renderer.render_inline(trace)
    assert len(inline_html) > 0, "Inline HTML should not be empty"
    print(f"✓ Inline HTML generated ({len(inline_html)} bytes)")
    
    print("✅ TreeTimelineRenderer tests passed!\n")


def test_timeline():
    """Test TimelineRenderer"""
    print("Testing TimelineRenderer...")
    
    # Create sample timeline data
    timeline = {
        'id': 'timeline-1',
        'title': 'Test Timeline',
        'duration_ms': 10000,
        'tracks': [
            {
                'name': 'Track 1',
                'segments': [
                    {'start_ms': 0, 'end_ms': 3000, 'label': 'Event 1'},
                    {'start_ms': 3500, 'end_ms': 7000, 'label': 'Event 2'}
                ]
            }
        ]
    }
    
    # Test renderer initialization
    renderer = TimelineRenderer()
    print("✓ TimelineRenderer initialized")
    
    # Test resource access
    css_content = renderer.get_css_content()
    assert len(css_content) > 0, "CSS content should not be empty"
    print(f"✓ CSS content loaded ({len(css_content)} bytes)")
    
    js_content = renderer.get_js_content()
    assert len(js_content) > 0, "JS content should not be empty"
    print(f"✓ JS content loaded ({len(js_content)} bytes)")
    
    # Test HTML generation
    output_path = '/tmp/test_timeline.html'
    renderer.render_to_html(
        timeline,
        output_path=output_path,
        title='Test Timeline'
    )
    assert Path(output_path).exists(), "HTML file should be created"
    print(f"✓ HTML file generated: {output_path}")
    
    # Test inline rendering
    inline_html = renderer.render_inline(timeline)
    assert len(inline_html) > 0, "Inline HTML should not be empty"
    print(f"✓ Inline HTML generated ({len(inline_html)} bytes)")
    
    print("✅ TimelineRenderer tests passed!\n")


def test_jinja2_integration():
    """Test Jinja2 integration"""
    print("Testing Jinja2 integration...")
    
    from jinja2 import Template
    
    renderer = TreeTimelineRenderer()
    
    # Test getting resources for custom template
    css = renderer.get_css_content()
    js = renderer.get_js_content()
    
    # Create a simple custom template
    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>{{ css }}</style>
    </head>
    <body>
        <div id="timeline"></div>
        <script>{{ js }}</script>
        <script>
            const renderer = new TreeTimelineRenderer({container: '#timeline'});
            renderer.render({{ trace_data | tojson }});
        </script>
    </body>
    </html>
    """
    
    template = Template(template_str)
    trace = create_trace_node('t1', 'Test', 'TRACE', 0, 1000)
    
    html = template.render(css=css, js=js, trace_data=trace)
    assert 'TreeTimelineRenderer' in html, "Template should contain renderer code"
    print("✓ Custom Jinja2 template rendered successfully")
    
    print("✅ Jinja2 integration tests passed!\n")


if __name__ == '__main__':
    print("=" * 60)
    print("cptools-web Package Tests")
    print("=" * 60)
    print()
    
    try:
        test_tree_timeline()
        test_timeline()
        test_jinja2_integration()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
