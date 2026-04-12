#!/usr/bin/env python3
"""
Chunked Translator for HTML content.

Handles translation of large HTML content by:
1. Splitting into manageable chunks
2. Using appropriate strategy based on backend type
3. Preserving HTML structure
"""

from typing import List

from .backends import OpenAIBackend, TranslationBackend
from .html_parser import HTMLParser


class ChunkedTranslator:
    """
    Handles translation of large HTML content by chunking.
    Preserves HTML structure while translating text content.
    
    Usage:
        backend = get_backend('openai')
        translator = ChunkedTranslator(backend)
        result = translator.translate_html(html_content, source_lang="zh", target_lang="en")
    """

    def __init__(self, backend: TranslationBackend):
        self.backend = backend
        self.parser = HTMLParser()

    def _is_smart_backend(self) -> bool:
        """Check if backend can handle HTML intelligently (like OpenAI)."""
        return isinstance(self.backend, OpenAIBackend)

    def translate_html(self, html_content: str, source_lang: str = "zh", target_lang: str = "en") -> str:
        """
        Translate HTML content, handling chunking for large documents.

        Args:
            html_content: HTML content to translate
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Translated HTML content
        """
        # For smart backends (OpenAI), send HTML directly with instructions
        if self._is_smart_backend():
            return self._translate_with_smart_backend(html_content, source_lang, target_lang)

        # For simple backends (Tencent TMT), extract text, translate, and reassemble
        return self._translate_with_simple_backend(html_content, source_lang, target_lang)

    def _translate_with_smart_backend(self, html_content: str, source_lang: str, target_lang: str) -> str:
        """Translate using a backend that understands HTML (like OpenAI)."""
        max_size = self.backend.max_chunk_size

        if len(html_content) <= max_size:
            return self.backend.translate(html_content, source_lang, target_lang)

        chunks = self._split_into_chunks(html_content, max_size)
        translated_chunks = []

        print(f"   📦 Splitting into {len(chunks)} chunks for translation...")

        for i, chunk in enumerate(chunks):
            print(f"   📝 Translating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
            translated = self.backend.translate(chunk, source_lang, target_lang)
            translated_chunks.append(translated)

        return ''.join(translated_chunks)

    def _translate_with_simple_backend(self, html_content: str, source_lang: str, target_lang: str) -> str:
        """Translate using a simple text backend (like Tencent TMT)."""
        def on_progress(current: int, total: int):
            if current % 10 == 0 or current == 1:
                print(f"   📝 Translating segment {current}/{total}...")

        def translate_fn(text: str) -> str:
            return self.backend.translate(text, source_lang, target_lang)

        # Get count of translatable texts first for logging
        translatable_count = len(self.parser.get_translatable_texts(html_content))

        if translatable_count == 0:
            print("   ℹ️  No translatable text found")
            return html_content

        print(f"   📦 Found {translatable_count} text segments to translate...")

        # Use BeautifulSoup-based translate method
        return self.parser.translate(html_content, translate_fn, on_progress)

    def _split_into_chunks(self, html: str, max_size: int) -> List[str]:
        """Split HTML into chunks at safe boundaries."""
        if len(html) <= max_size:
            return [html]

        chunks = []
        pos = 0

        while pos < len(html):
            if pos + max_size >= len(html):
                chunks.append(html[pos:])
                break

            end = pos + max_size
            split_pos = self._find_split_point(html, pos, end)

            chunks.append(html[pos:split_pos])
            pos = split_pos

        return chunks

    def _find_split_point(self, html: str, start: int, end: int) -> int:
        """Find a safe split point near end position."""
        search_start = max(start, end - 500)
        segment = html[search_start:end]

        # Find the last complete closing tag
        close_tags = [
            '</table>', '</tr>', '</td>', '</th>',
            '</div>', '</p>', '</li>', '</ul>', '</ol>',
            '</h1>', '</h2>', '</h3>', '</h4>',
            '</ac:rich-text-body>', '</ac:structured-macro>',
        ]

        best_pos = -1
        for tag in close_tags:
            pos = segment.rfind(tag)
            if pos != -1:
                actual_pos = search_start + pos + len(tag)
                if actual_pos > best_pos:
                    best_pos = actual_pos

        if best_pos > start:
            return best_pos

        # Fallback: split at any > character
        pos = segment.rfind('>')
        while pos > 0:
            before = segment[:pos]
            double_quotes = before.count('"')
            single_quotes = before.count("'")
            
            if double_quotes % 2 == 0 and single_quotes % 2 == 0:
                return search_start + pos + 1
            
            pos = segment.rfind('>', 0, pos)

        return end

