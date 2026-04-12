#!/usr/bin/env python3
"""
OpenAI GPT-based translation backend.

Environment variables:
- OPENAI_API_KEY: API key (required)
- OPENAI_BASE_URL: Base URL (optional, default: https://api.openai.com/v1)
"""

import os
from typing import Optional

import requests

from .base import TranslationBackend


class OpenAIBackend(TranslationBackend):
    """
    OpenAI GPT-based translation backend.
    
    Advantages:
    - Handles HTML content intelligently
    - Better context understanding
    - Can preserve technical terms
    
    Args:
        api_key: OpenAI API key (or set OPENAI_API_KEY env var)
        base_url: API base URL (or set OPENAI_BASE_URL env var)
        model: Model to use (default: gpt-4o)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o"
    ):
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.base_url = base_url or os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = model
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
    
    @property
    def name(self) -> str:
        return f"OpenAI ({self.model})"
    
    @property
    def max_chunk_size(self) -> int:
        return 30000  # OpenAI can handle larger chunks
    
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate using OpenAI API."""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        prompt = f"""Translate the following content to {target_lang}.

IMPORTANT RULES:
1. Keep ALL HTML tags and structure exactly as they are
2. Only translate the text content between tags
3. Do NOT translate code blocks, URLs, file paths, or technical identifiers
4. Keep table structures intact
5. Preserve all Confluence macros (like <ac:...> tags)
6. Keep image references and attachments unchanged
7. Maintain the same formatting and layout

Content to translate:
{text}"""

        data = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': 'You are a professional translator. Translate content while preserving all HTML structure and technical terms.'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.3
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content']

