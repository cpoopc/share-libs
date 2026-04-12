#!/usr/bin/env python3
"""
Translation backends package.

Available backends:
- openai: OpenAI GPT-based translation (handles HTML intelligently)
- tencent/tmt: Tencent Cloud Machine Translation
"""

from typing import List

from .base import TranslationBackend
from .openai import OpenAIBackend
from .tencent import TencentTMTBackend


def get_backend(name: str, **kwargs) -> TranslationBackend:
    """
    Factory function to get a translation backend by name.

    Args:
        name: Backend name ('openai', 'tencent', etc.)
        **kwargs: Additional arguments for the backend

    Returns:
        TranslationBackend instance
        
    Example:
        >>> backend = get_backend('openai', model='gpt-4o')
        >>> backend = get_backend('tencent', region='ap-guangzhou')
    """
    backends = {
        'openai': OpenAIBackend,
        'tencent': TencentTMTBackend,
        'tmt': TencentTMTBackend,
    }

    name_lower = name.lower()
    if name_lower not in backends:
        available = ', '.join(backends.keys())
        raise ValueError(f"Unknown backend: {name}. Available: {available}")

    return backends[name_lower](**kwargs)


def list_backends() -> List[str]:
    """List available translation backend names."""
    return ['openai', 'tencent']


__all__ = [
    'TranslationBackend',
    'OpenAIBackend',
    'TencentTMTBackend',
    'get_backend',
    'list_backends',
]

