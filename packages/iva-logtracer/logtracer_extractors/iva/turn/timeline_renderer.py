#!/usr/bin/env python3
"""
IVA Timeline Renderer - 使用树形时间线渲染器生成HTML

使用Jinja2模板和树形时间线JavaScript组件生成可视化HTML报告。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from cptools_web import TreeTimelineRenderer as WebRenderer
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Try relative import first, fall back to absolute
try:
    from .timeline_converter import convert_call_session_to_tree, convert_turn_to_tree
except ImportError:
    from timeline_converter import convert_call_session_to_tree, convert_turn_to_tree


class TurnTimelineRenderer:
    """Turn时间线渲染器"""
    
    def __init__(self, template_dir: Optional[Path] = None):
        """
        初始化渲染器
        
        Args:
            template_dir: 模板目录路径,默认为当前模块的templates目录
        """
        if template_dir is None:
            template_dir = Path(__file__).parent / 'templates'
        
        self.template_dir = template_dir
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Initialize web renderer for resource access
        self.web_renderer = WebRenderer()
    
    def render_turn(self, turn: 'Turn', output_path: str, 
                   turn_index: int = 0, **kwargs) -> str:
        """
        渲染单个Turn的时间线HTML
        
        Args:
            turn: Turn对象
            output_path: 输出HTML文件路径
            turn_index: Turn索引
            **kwargs: 额外的模板变量
            
        Returns:
            生成的HTML文件路径
        """
        # 转换为树形结构
        tree_data = convert_turn_to_tree(turn, turn_index)
        
        if not tree_data:
            raise ValueError(f"Failed to convert turn {turn_index} to tree structure")
        
        # 准备模板变量
        context = {
            'title': f'Turn {turn.turn_number} Timeline',
            'description': f'Turn {turn.turn_number} 组件时序分析',
            'metadata': {
                'Turn Number': turn.turn_number,
                'Duration': f'{turn.duration_ms:.2f}ms',
                'TTFT': f'{turn.ttft_ms:.2f}ms' if turn.ttft_ms else 'N/A',
                'User Input': turn.user_transcript[:50] + '...' if turn.user_transcript and len(turn.user_transcript) > 50 else turn.user_transcript or 'N/A',
            },
            'trace_data': tree_data,
            **kwargs
        }
        
        # Add CSS/JS resources
        context['timeline_css'] = self.web_renderer.get_css_content()
        context['timeline_js'] = self.web_renderer.get_js_content()
        
        # 渲染模板
        template = self.env.get_template('tree-timeline.j2')
        html = template.render(**context)
        
        # 写入文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')
        
        return str(output_file)
    
    def render_call_session(self, turns: List['Turn'], output_path: str, 
                           session_id: Optional[str] = None,
                           conversation_id: Optional[str] = None,
                           **kwargs) -> str:
        """
        渲染整通电话的所有Turn时间线
        
        Args:
            turns: Turn对象列表
            output_path: 输出HTML文件路径
            session_id: 会话ID
            conversation_id: 对话ID
            **kwargs: 额外的模板变量
            
        Returns:
            生成的HTML文件路径
        """
        # 转换所有Turn为树形结构
        tree_data_list = convert_call_session_to_tree(turns)
        
        if not tree_data_list:
            raise ValueError("Failed to convert any turns to tree structure")
        
        # 计算汇总信息
        total_duration = sum(turn.duration_ms for turn in turns)
        avg_ttft = sum(turn.ttft_ms for turn in turns if turn.ttft_ms) / len([t for t in turns if t.ttft_ms]) if any(turn.ttft_ms for turn in turns) else 0
        
        # 准备模板变量
        context = {
            'title': f'Call Session Timeline',
            'description': f'完整通话时序分析 - {len(turns)} Turns',
            'metadata': {
                'Session ID': session_id or 'N/A',
                'Conversation ID': conversation_id or 'N/A',
                'Total Turns': len(turns),
                'Total Duration': f'{total_duration:.2f}ms',
                'Avg TTFT': f'{avg_ttft:.2f}ms' if avg_ttft > 0 else 'N/A',
            },
            'trace_data_list': tree_data_list,  # 多个Turn
            'is_multi_turn': True,
            **kwargs
        }
        
        # Add CSS/JS resources
        context['timeline_css'] = self.web_renderer.get_css_content()
        context['timeline_js'] = self.web_renderer.get_js_content()
        
        # 渲染模板
        template = self.env.get_template('tree-timeline-multi.j2')
        html = template.render(**context)
        
        # 写入文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')
        
        return str(output_file)
    
    def render_turn_comparison(self, turns: List['Turn'], output_path: str,
                              **kwargs) -> str:
        """
        渲染多个Turn的对比视图
        
        Args:
            turns: Turn对象列表
            output_path: 输出HTML文件路径
            **kwargs: 额外的模板变量
            
        Returns:
            生成的HTML文件路径
        """
        # 转换所有Turn
        tree_data_list = convert_call_session_to_tree(turns)
        
        # 准备对比数据
        comparison_data = []
        for i, (turn, tree_data) in enumerate(zip(turns, tree_data_list)):
            comparison_data.append({
                'turn_number': turn.turn_number,
                'duration_ms': turn.duration_ms,
                'ttft_ms': turn.ttft_ms,
                'tree_data': tree_data
            })
        
        context = {
            'title': 'Turn Comparison',
            'description': f'对比 {len(turns)} 个Turn的性能',
            'comparison_data': comparison_data,
            **kwargs
        }
        
        # 渲染模板
        template = self.env.get_template('tree-timeline-comparison.j2')
        html = template.render(**context)
        
        # 写入文件
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')
        
        return str(output_file)


def generate_timeline_html(turns: List['Turn'], output_dir: Path,
                          session_id: Optional[str] = None,
                          conversation_id: Optional[str] = None) -> List[str]:
    """
    生成时间线HTML文件
    
    Args:
        turns: Turn对象列表
        output_dir: 输出目录
        session_id: 会话ID
        conversation_id: 对话ID
        
    Returns:
        生成的HTML文件路径列表
    """
    renderer = TurnTimelineRenderer()
    generated_files = []
    
    # 1. 生成整体会话时间线
    session_file = output_dir / 'timeline_session.html'
    try:
        renderer.render_call_session(
            turns, 
            str(session_file),
            session_id=session_id,
            conversation_id=conversation_id
        )
        generated_files.append(str(session_file))
    except Exception as e:
        print(f"Warning: Failed to generate session timeline: {e}")
    
    # 2. 为每个Turn生成单独的时间线
    for i, turn in enumerate(turns):
        turn_file = output_dir / f'timeline_turn_{turn.turn_number}.html'
        try:
            renderer.render_turn(turn, str(turn_file), turn_index=i)
            generated_files.append(str(turn_file))
        except Exception as e:
            print(f"Warning: Failed to generate timeline for turn {turn.turn_number}: {e}")
    
    return generated_files
