"""
Timeline Renderer - Python wrapper for timeline visualization component
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from importlib.resources import files
except ImportError:
    # Python < 3.9 fallback
    from importlib_resources import files


class TimelineRenderer:
    """Python wrapper for the timeline JavaScript renderer"""
    
    def __init__(self):
        """Initialize the renderer"""
        self._package_path = files('cptools_web')
    
    def get_css_content(self) -> str:
        """
        Get the CSS content as a string
        
        Returns:
            CSS file content
        """
        css_file = self._package_path / 'resources' / 'css' / 'timeline-renderer.css'
        return css_file.read_text(encoding='utf-8')
    
    def get_js_content(self) -> str:
        """
        Get the JavaScript content as a string
        
        Returns:
            JavaScript file content
        """
        js_file = self._package_path / 'resources' / 'js' / 'timeline-renderer.js'
        return js_file.read_text(encoding='utf-8')
    
    def get_css_path(self) -> Path:
        """
        Get the path to the CSS file
        
        Returns:
            Path object pointing to the CSS file
        """
        css_file = self._package_path / 'resources' / 'css' / 'timeline-renderer.css'
        try:
            return Path(str(css_file))
        except:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
            temp_dir.mkdir(exist_ok=True)
            temp_css = temp_dir / 'timeline-renderer.css'
            temp_css.write_text(self.get_css_content(), encoding='utf-8')
            return temp_css
    
    def get_js_path(self) -> Path:
        """
        Get the path to the JavaScript file
        
        Returns:
            Path object pointing to the JavaScript file
        """
        js_file = self._package_path / 'resources' / 'js' / 'timeline-renderer.js'
        try:
            return Path(str(js_file))
        except:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
            temp_dir.mkdir(exist_ok=True)
            temp_js = temp_dir / 'timeline-renderer.js'
            temp_js.write_text(self.get_js_content(), encoding='utf-8')
            return temp_js
    
    def render_to_html(self,
                      timeline_data: Dict[str, Any],
                      output_path: str = "timeline.html",
                      title: str = "Timeline Visualization",
                      on_segment_click_callback: str = "",
                      on_marker_click_callback: str = "") -> str:
        """
        Render timeline data to an HTML file
        
        Args:
            timeline_data: Timeline data dictionary
            output_path: Output HTML file path
            title: Page title
            on_segment_click_callback: Optional JavaScript callback for segment clicks
            on_marker_click_callback: Optional JavaScript callback for marker clicks
            
        Returns:
            Path to generated HTML file
        """
        css_content = self.get_css_content()
        js_content = self.get_js_content()
        
        # Build callbacks
        segment_callback = on_segment_click_callback or "console.log('Segment clicked:', segment);"
        marker_callback = on_marker_click_callback or "console.log('Marker clicked:', marker);"
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css_content}</style>
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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div id="timeline-container"></div>
    </div>
    
    <script>{js_content}</script>
    <script>
        const timelineData = {json.dumps(timeline_data, indent=2)};
        
        const renderer = new TimelineRenderer({{
            container: '#timeline-container',
            onSegmentClick: (segment, track, timeline, event) => {{
                {segment_callback}
            }},
            onMarkerClick: (marker, track, timeline, event) => {{
                {marker_callback}
            }}
        }});
        
        renderer.render(timelineData);
    </script>
</body>
</html>"""
        
        Path(output_path).write_text(html, encoding='utf-8')
        return output_path
    
    def render_inline(self, timeline_data: Dict[str, Any]) -> str:
        """
        Render timeline data to inline HTML (for Jupyter notebooks)
        
        Args:
            timeline_data: Timeline data dictionary
            
        Returns:
            HTML string with inline CSS and JS
        """
        css_content = self.get_css_content()
        js_content = self.get_js_content()
        
        html = f"""
<div id="timeline-inline-{id(timeline_data)}">
    <style>{css_content}</style>
    <div id="container-{id(timeline_data)}"></div>
</div>
<script>
{js_content}

const timelineData_{id(timeline_data)} = {json.dumps(timeline_data)};
const renderer_{id(timeline_data)} = new TimelineRenderer({{
    container: '#container-{id(timeline_data)}',
    onSegmentClick: (segment) => console.log('Segment clicked:', segment)
}});
renderer_{id(timeline_data)}.render(timelineData_{id(timeline_data)});
</script>
"""
        return html
