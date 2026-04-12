#!/usr/bin/env python3
"""
HTML Parser for content translation.

Uses BeautifulSoup for robust HTML parsing while preserving structure.
Provides functionality to:
1. Parse HTML and identify translatable text nodes
2. Track no-translate regions (code blocks, macros)
3. Apply translations while preserving structure

Round-trip guarantees:
- Preserves all HTML structure (tags, attributes, nesting)
- Restores self-closing tags (e.g., <ri:page/>) that BeautifulSoup expands
- Uses minimal escaping to preserve original attribute values
- Minor whitespace normalization in self-closing tags: `<hr />` → `<hr/>`
"""

import re
from typing import Callable, List, Optional, Tuple

from bs4 import BeautifulSoup, CData, Comment, Doctype, NavigableString, ProcessingInstruction

# Pattern for restoring self-closing tags that BeautifulSoup expands
# Matches: <tag-name attrs></tag-name> or <tag-name attrs>  </tag-name> (whitespace only)
_EMPTY_ELEMENT_PATTERN = re.compile(r'<([\w:-]+)(\s+[^>]*)?>(\s*)</\1>')


def _restore_self_closing_tags(html: str) -> str:
    """
    Convert empty elements back to self-closing form.
    
    BeautifulSoup expands self-closing tags like <ri:page/> to <ri:page></ri:page>.
    This function restores them to the original self-closing form.
    """
    def replace(match):
        tag_name = match.group(1)
        attrs = match.group(2) or ''
        whitespace = match.group(3)
        if not whitespace.strip():
            return f'<{tag_name}{attrs}/>'
        return match.group(0)
    
    return _EMPTY_ELEMENT_PATTERN.sub(replace, html)


class HTMLParser:
    """
    BeautifulSoup-based parser for HTML content translation.

    Main API:
    - translate(html, translate_fn) - Translate HTML preserving structure
    - get_translatable_texts(html) - Extract translatable text list
    """

    # Tags whose content should NOT be translated
    NO_TRANSLATE_TAGS = {
        'code', 'pre', 'script', 'style', 'kbd', 'samp', 'var',
        'ac:plain-text-body',
        'ac:parameter',
    }

    # Confluence macro names whose content should NOT be translated
    NO_TRANSLATE_MACROS = {
        'code', 'noformat',
        'jira', 'anchor', 'include', 'excerpt-include',
        'toc', 'toc-zone',
        'attachments', 'children', 'recently-updated', 'pagetree', 'livesearch',
        'chart', 'gliffy', 'drawio',
        'html', 'widget', 'iframe',
        'status',
    }

    # HTML5 void elements (no closing tag needed)
    VOID_ELEMENTS = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr',
    }

    @staticmethod
    def is_technical_content(text: str) -> bool:
        """Check if text looks like code or technical content that shouldn't be translated."""
        text = text.strip()
        if not text:
            return True

        # Skip HTML entities only (like &nbsp;)
        if re.match(r'^&\w+;$', text):
            return True

        # Skip if mostly non-word characters (code, punctuation)
        word_chars = sum(1 for c in text if c.isalnum() or c in ' \t\n')
        if len(text) > 0 and word_chars / len(text) < 0.3:
            return True

        # Skip very short text (likely labels, IDs)
        if len(text) < 2:
            return True

        # Skip URLs
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', text):
            return True

        # Skip if looks like a path or code
        if re.match(r'^[\w./_-]+$', text) and ('/' in text or '.' in text):
            return True

        # Skip if looks like a variable or identifier
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', text) and len(text) > 20:
            return True

        return False

    @staticmethod
    def preserve_whitespace(original: str, translated: str) -> str:
        """Preserve leading/trailing whitespace from original text."""
        leading_ws = original[:len(original) - len(original.lstrip())]
        trailing_ws = original[len(original.rstrip()):]
        return leading_ws + translated.strip() + trailing_ws

    def translate(
        self,
        html: str,
        translate_fn: Callable[[str], str],
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Translate HTML content using BeautifulSoup.

        Args:
            html: HTML content to translate
            translate_fn: Function that takes text and returns translated text
            on_progress: Optional callback(current, total) for progress reporting

        Returns:
            Translated HTML with structure preserved
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Collect all translatable text nodes
        text_nodes = self._collect_text_nodes(soup)
        translatable = [
            (i, node, original)
            for i, (node, original, is_trans) in enumerate(text_nodes)
            if is_trans and original.strip() and not self.is_technical_content(original)
        ]

        total = len(translatable)
        for count, (_, node, original) in enumerate(translatable):
            if on_progress:
                on_progress(count + 1, total)

            try:
                stripped = original.strip()
                translated = translate_fn(stripped)

                if translated and translated.strip():
                    new_text = self.preserve_whitespace(original, translated)
                    node.replace_with(NavigableString(new_text))
            except Exception:
                # Keep original on error
                pass

        # Use formatter=None for minimal escaping, then restore self-closing tags
        output = soup.decode(formatter=None)
        return _restore_self_closing_tags(output)

    def _collect_text_nodes(self, soup: BeautifulSoup) -> List[Tuple[NavigableString, str, bool]]:
        """Collect all text nodes with their translatable status."""
        result = []

        for node in soup.descendants:
            if isinstance(node, NavigableString):
                # Skip special nodes (comments, CDATA, etc.)
                if isinstance(node, (Comment, CData, Doctype, ProcessingInstruction)):
                    continue

                original = str(node)
                is_translatable = self._is_translatable_node(node)
                result.append((node, original, is_translatable))

        return result

    def _is_translatable_node(self, node: NavigableString) -> bool:
        """Check if a text node should be translated based on its parent context."""
        for parent in node.parents:
            if parent.name is None:
                continue

            parent_name = parent.name.lower()

            # Check no-translate tags
            if parent_name in self.NO_TRANSLATE_TAGS:
                return False

            # Check Confluence macros
            if parent_name == 'ac:structured-macro':
                macro_name = parent.get('ac:name', '')
                if macro_name.lower() in self.NO_TRANSLATE_MACROS:
                    return False

        return True

    def get_translatable_texts(self, html: str) -> List[Tuple[int, str]]:
        """
        Get all translatable texts from HTML (for batch translation).

        Args:
            html: HTML content to parse

        Returns:
            List of (index, stripped_text) tuples
        """
        soup = BeautifulSoup(html, 'html.parser')
        text_nodes = self._collect_text_nodes(soup)

        result = []
        for i, (_, original, is_trans) in enumerate(text_nodes):
            if is_trans and original.strip() and not self.is_technical_content(original):
                result.append((i, original.strip()))

        return result

