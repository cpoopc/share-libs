"""
Tree Timeline Renderer - Python wrapper for tree-timeline visualization component
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from importlib.resources import files
except ImportError:
    # Python < 3.9 fallback
    from importlib_resources import files

from jinja2 import Environment, FileSystemLoader


class TreeTimelineRenderer:
    """Python wrapper for the tree-timeline JavaScript renderer"""
    
    def __init__(self):
        """Initialize the renderer"""
        self._package_path = files('cptools_web')
    
    def get_css_content(self) -> str:
        """
        Get the CSS content as a string
        
        Returns:
            CSS file content
        """
        css_file = self._package_path / 'resources' / 'css' / 'tree-timeline-renderer.css'
        return css_file.read_text(encoding='utf-8')
    
    def get_js_content(self) -> str:
        """
        Get the JavaScript content as a string
        
        Returns:
            JavaScript file content
        """
        js_file = self._package_path / 'resources' / 'js' / 'tree-timeline-renderer.js'
        return js_file.read_text(encoding='utf-8')
    
    def get_css_path(self) -> Path:
        """
        Get the path to the CSS file
        
        Returns:
            Path object pointing to the CSS file
        """
        # For Python 3.9+, files() returns a Traversable, we need to convert to Path
        css_file = self._package_path / 'resources' / 'css' / 'tree-timeline-renderer.css'
        # Try to get the actual file path if possible
        try:
            return Path(str(css_file))
        except:
            # If the package is in a zip, we need to extract it
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
            temp_dir.mkdir(exist_ok=True)
            temp_css = temp_dir / 'tree-timeline-renderer.css'
            temp_css.write_text(self.get_css_content(), encoding='utf-8')
            return temp_css
    
    def get_js_path(self) -> Path:
        """
        Get the path to the JavaScript file
        
        Returns:
            Path object pointing to the JavaScript file
        """
        js_file = self._package_path / 'resources' / 'js' / 'tree-timeline-renderer.js'
        try:
            return Path(str(js_file))
        except:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
            temp_dir.mkdir(exist_ok=True)
            temp_js = temp_dir / 'tree-timeline-renderer.js'
            temp_js.write_text(self.get_js_content(), encoding='utf-8')
            return temp_js
    
    def get_template_path(self) -> Path:
        """
        Get the path to the Jinja2 template file
        
        Returns:
            Path object pointing to the template file
        """
        template_file = self._package_path / 'resources' / 'templates' / 'tree-timeline-template.j2'
        try:
            return Path(str(template_file))
        except:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
            temp_dir.mkdir(exist_ok=True)
            temp_template = temp_dir / 'tree-timeline-template.j2'
            temp_template.write_text(self.get_template_content(), encoding='utf-8')
            return temp_template
    
    def get_template_content(self) -> str:
        """
        Get the Jinja2 template content as a string
        
        Returns:
            Template file content
        """
        template_file = self._package_path / 'resources' / 'templates' / 'tree-timeline-template.j2'
        return template_file.read_text(encoding='utf-8')
    
    def get_jinja_env(self) -> Environment:
        """
        Get a configured Jinja2 environment with the package templates
        
        Returns:
            Jinja2 Environment configured with package templates
        """
        # Create a temporary directory with templates
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / 'cptools_web_resources'
        temp_dir.mkdir(exist_ok=True)
        
        # Write template to temp directory
        template_path = temp_dir / 'tree-timeline-template.j2'
        template_path.write_text(self.get_template_content(), encoding='utf-8')
        
        return Environment(loader=FileSystemLoader(str(temp_dir)))
    
    def render_to_html(self, 
                      trace_data: Dict[str, Any],
                      output_path: str = "timeline.html",
                      title: str = "Trace Timeline",
                      description: str = "",
                      metadata: Optional[Dict[str, Any]] = None,
                      on_node_click_callback: str = "") -> str:
        """
        Render trace data to an HTML file using the built-in Jinja2 template
        
        Args:
            trace_data: Hierarchical trace data dictionary
            output_path: Output HTML file path
            title: Page title
            description: Optional description text
            metadata: Optional metadata dictionary to display
            on_node_click_callback: Optional JavaScript callback code for node clicks
            
        Returns:
            Path to generated HTML file
        """
        env = self.get_jinja_env()
        template = env.get_template('tree-timeline-template.j2')
        
        context = {
            'title': title,
            'description': description,
            'metadata': metadata or {},
            'trace_data': trace_data,
            'on_node_click_callback': on_node_click_callback
        }
        
        html = template.render(**context)
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
        css_content = self.get_css_content()
        js_content = self.get_js_content()
        
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


def create_trace_node(node_id: str, 
                     name: str, 
                     node_type: str,
                     start_ms: float, 
                     end_ms: float,
                     children: Optional[List[Dict]] = None) -> Dict[str, Any]:
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
