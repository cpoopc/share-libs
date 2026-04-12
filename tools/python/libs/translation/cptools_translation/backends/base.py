#!/usr/bin/env python3
"""
Abstract base class for translation backends.
"""

from abc import ABC, abstractmethod


class TranslationBackend(ABC):
    """
    Abstract base class for translation backends.
    
    All translation backends must implement:
    - translate(): Core translation method
    - name: Human-readable backend name
    - max_chunk_size: Maximum text size per request
    """
    
    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translate text from source language to target language.
        
        Args:
            text: Text to translate
            source_lang: Source language code (e.g., 'zh', 'en', 'auto')
            target_lang: Target language code (e.g., 'en', 'zh')
            
        Returns:
            Translated text
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this backend."""
        pass
    
    @property
    @abstractmethod
    def max_chunk_size(self) -> int:
        """Maximum text size per request."""
        pass

