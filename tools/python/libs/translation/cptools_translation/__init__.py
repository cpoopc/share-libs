#!/usr/bin/env python3
"""
Translation library for text and HTML content.

This module provides:
- Multiple translation backends (OpenAI, Tencent TMT)
- HTML-aware parsing and reassembly
- Chunked translation for large documents

Usage:
    from cptools_translation import get_backend, ChunkedTranslator

    # Get a backend
    backend = get_backend('openai')

    # Simple text translation
    result = backend.translate("Hello", source_lang="en", target_lang="zh")

    # HTML translation with structure preservation
    translator = ChunkedTranslator(backend)
    html_result = translator.translate_html(html_content, source_lang="en", target_lang="zh")

Environment Variables:
    OPENAI_API_KEY      - OpenAI API key (for openai backend)
    OPENAI_BASE_URL     - OpenAI base URL (optional)
    TENCENT_SECRET_ID   - Tencent Cloud SecretId (for tencent backend)
    TENCENT_SECRET_KEY  - Tencent Cloud SecretKey (for tencent backend)

    You can also create a .env file in this package directory.
"""

from pathlib import Path

from cptools_common import load_dotenv

# Auto-load .env from this package's directory (low priority, won't override existing env vars)
_PACKAGE_DIR = Path(__file__).parent.parent
load_dotenv(_PACKAGE_DIR / '.env')

from .backends import (
    OpenAIBackend,
    TencentTMTBackend,
    TranslationBackend,
    get_backend,
    list_backends,
)
from .html_parser import HTMLParser
from .translator import ChunkedTranslator

__all__ = [
    # Backends
    'TranslationBackend',
    'OpenAIBackend',
    'TencentTMTBackend',
    'get_backend',
    'list_backends',
    # Parser
    'HTMLParser',
    # Translator
    'ChunkedTranslator',
]

