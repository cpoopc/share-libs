#!/usr/bin/env python3
"""
Confluence Page Translator
Translate a Confluence wiki page to English and update it directly.

Supports multiple translation backends:
- OpenAI (GPT-4o, etc.)
- Tencent Cloud TMT (Machine Translation)

Install dependencies:
    uv sync
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Import from shared libs
from cptools_common import get_project_root, load_dotenv
from cptools_translation import ChunkedTranslator, get_backend, list_backends

# Load .env files (priority: env vars > app .env > project root .env)
_APP_DIR = Path(__file__).resolve().parent.parent
load_dotenv(
    get_project_root() / '.env',  # 项目根目录（低优先级）
    _APP_DIR / '.env',            # app 目录（高优先级）
)

# Import local modules
try:
    from .confluence_client import ConfluenceClient
    from .sync_config import SyncConfig
except ImportError:
    from confluence_client import ConfluenceClient
    from sync_config import SyncConfig


class ConfluenceTranslator:
    """Translator for Confluence wiki pages."""

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        use_bearer_token: bool = False,
        translation_backend: str = "openai",
        model: str = "gpt-4o",
        skip_translation_init: bool = False
    ):
        """
        Initialize Confluence translator.

        Args:
            base_url: Confluence base URL
            username: Confluence username/email
            api_token: Confluence API token
            use_bearer_token: Use Bearer token auth instead of Basic Auth
            translation_backend: Translation backend ('openai', 'tencent')
            model: Model to use (for OpenAI backend)
            skip_translation_init: Skip translation backend initialization (for download/upload only)
        """
        self.base_url = base_url.rstrip('/')
        self.translation_backend_name = translation_backend
        self.model = model

        # Initialize Confluence client using atlassian-python-api
        self.client = ConfluenceClient(
            base_url=base_url,
            username=username,
            api_token=api_token,
            use_bearer_token=use_bearer_token,
        )

        # Translation backend setup
        self.translator = None
        if not skip_translation_init:
            self._init_translation_backend()

    def _init_translation_backend(self):
        """Initialize the translation backend."""
        try:
            if self.translation_backend_name.lower() == 'openai':
                backend = get_backend('openai', model=self.model)
            else:
                backend = get_backend(self.translation_backend_name)
            self.translator = ChunkedTranslator(backend)
            print(f"🌐 Translation backend: {backend.name}")
        except ValueError as e:
            raise ValueError(f"Failed to initialize translation backend: {e}")

    @classmethod
    def from_config(cls, config: SyncConfig, **kwargs) -> "ConfluenceTranslator":
        """Create translator from SyncConfig."""
        return cls(
            base_url=config.confluence_url,
            username=config.auth.username,
            api_token=config.auth.token,
            use_bearer_token=config.auth.use_bearer,
            **kwargs
        )

    def get_page_id_from_url(self, url: str) -> str:
        """Extract page ID from Confluence URL."""
        # Match patterns like /pages/123456789/ or /pages/123456789
        match = re.search(r'/pages/(\d+)', url)
        if match:
            return match.group(1)
        raise ValueError(f"Cannot extract page ID from URL: {url}")

    def get_page(self, page_id: str) -> dict:
        """Get page content from Confluence."""
        page = self.client.get_page_by_id(page_id, expand='body.storage,version,space')
        if not page:
            raise ValueError(f"Page {page_id} not found")
        return page

    def translate_content(self, html_content: str, source_lang: str = "zh", target_lang: str = "en") -> str:
        """Translate HTML content using the configured backend."""
        if not self.translator:
            raise ValueError("Translation backend not initialized. Call _init_translation_backend() first.")
        return self.translator.translate_html(html_content, source_lang, target_lang)

    def update_page(self, page_id: str, title: str, content: str, version: int, space_key: str) -> dict:
        """Update page content in Confluence."""
        # The atlassian-python-api handles version increment internally
        return self.client.update_page(
            page_id=page_id,
            title=title,
            body=content,
        )

    def download_page(self, page_input: str, output_file: Optional[str] = None) -> bool:
        """
        Download page content to a local file for manual translation.

        Args:
            page_input: Page ID or URL
            output_file: Output file path (default: page_<id>.html)

        Returns:
            True if successful, False otherwise
        """
        # Determine page ID
        if page_input.startswith('http'):
            page_id = self.get_page_id_from_url(page_input)
            print(f"📄 Extracted page ID: {page_id}")
        else:
            page_id = page_input

        # Get page content
        print(f"📥 Fetching page {page_id}...")
        try:
            page = self.get_page(page_id)
        except Exception as e:
            print(f"❌ Error fetching page: {e}")
            return False

        title = page['title']
        version = page['version']['number']
        space_key = page['space']['key']
        html_content = page['body']['storage']['value']

        print(f"📄 Page: {title}")
        print(f"   Space: {space_key}")
        print(f"   Version: {version}")
        print(f"   Content length: {len(html_content)} chars")

        # Determine output file
        if not output_file:
            safe_title = re.sub(r'[^\w\-]', '_', title)[:50]
            output_file = f"page_{page_id}_{safe_title}.html"

        # Save metadata as JSON alongside
        metadata = {
            'page_id': page_id,
            'title': title,
            'space_key': space_key,
            'version': version,
            'base_url': self.base_url
        }

        metadata_file = output_file.rsplit('.', 1)[0] + '.json'

        import json
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"💾 Metadata saved: {metadata_file}")

        # Save content
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"💾 Content saved: {output_file}")

        print(f"\n📝 翻译步骤:")
        print(f"   1. 编辑 {output_file} 进行翻译")
        print(f"   2. 保留所有 HTML 标签和 Confluence 宏 (<ac:...>)")
        print(f"   3. 运行: confluence-sync translate upload {output_file}")

        return True

    def upload_page(self, content_file: str, metadata_file: Optional[str] = None) -> bool:
        """
        Upload translated content to Confluence.

        Args:
            content_file: Path to the translated HTML content file
            metadata_file: Path to metadata JSON file (default: auto-detect)

        Returns:
            True if successful, False otherwise
        """
        import json

        # Auto-detect metadata file
        if not metadata_file:
            metadata_file = content_file.rsplit('.', 1)[0] + '.json'

        # Load metadata
        print(f"📄 Loading metadata: {metadata_file}")
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except FileNotFoundError:
            print(f"❌ Metadata file not found: {metadata_file}")
            return False

        page_id = metadata['page_id']
        title = metadata['title']
        space_key = metadata['space_key']
        old_version = metadata['version']

        # Load content
        print(f"📄 Loading content: {content_file}")
        try:
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"❌ Content file not found: {content_file}")
            return False

        print(f"📄 Page: {title}")
        print(f"   Space: {space_key}")
        print(f"   Old version: {old_version}")
        print(f"   Content length: {len(content)} chars")

        # Get current version to avoid conflicts
        print(f"\n🔍 Checking current version...")
        try:
            current_page = self.get_page(page_id)
            current_version = current_page['version']['number']
            if current_version != old_version:
                print(f"⚠️  Warning: Page has been modified since download!")
                print(f"   Downloaded version: {old_version}")
                print(f"   Current version: {current_version}")
                response = input("   Continue anyway? (y/N): ")
                if response.lower() != 'y':
                    print("❌ Aborted")
                    return False
        except Exception as e:
            print(f"❌ Error checking page: {e}")
            return False

        # Update page
        print(f"\n📤 Updating page...")
        try:
            result = self.update_page(page_id, title, content, current_version, space_key)
            new_version = result['version']['number']
            print(f"✅ Page updated successfully! (version {current_version} → {new_version})")
            print(f"🔗 {self.base_url}{result['_links']['webui']}")
            return True
        except Exception as e:
            print(f"❌ Error updating page: {e}")
            return False

    def translate_page(
        self,
        page_input: str,
        source_lang: str = "zh",
        target_lang: str = "en",
        dry_run: bool = False
    ) -> bool:
        """
        Translate a Confluence page to the target language.

        Args:
            page_input: Page ID or URL
            source_lang: Source language code (default: zh)
            target_lang: Target language code (default: en)
            dry_run: If True, only show what would be done without making changes

        Returns:
            True if successful, False otherwise
        """
        # Determine page ID
        if page_input.startswith('http'):
            page_id = self.get_page_id_from_url(page_input)
            print(f"📄 Extracted page ID: {page_id}")
        else:
            page_id = page_input

        # Get page content
        print(f"📥 Fetching page {page_id}...")
        try:
            page = self.get_page(page_id)
        except Exception as e:
            print(f"❌ Error fetching page: {e}")
            return False

        title = page['title']
        version = page['version']['number']
        space_key = page['space']['key']
        html_content = page['body']['storage']['value']

        print(f"📄 Page: {title}")
        print(f"   Space: {space_key}")
        print(f"   Version: {version}")
        print(f"   Content length: {len(html_content)} chars")

        if not html_content.strip():
            print("⚠️  Page has no content to translate")
            return False

        # Translate content
        print(f"\n🌐 Translating from {source_lang} to {target_lang}...")
        try:
            translated_content = self.translate_content(html_content, source_lang, target_lang)
        except Exception as e:
            print(f"❌ Translation error: {e}")
            return False

        print(f"✅ Translation complete ({len(translated_content)} chars)")

        if dry_run:
            print("\n🔍 Dry run mode - not updating page")
            print("\n--- Translated content preview (first 500 chars) ---")
            print(translated_content[:500])
            print("...")
            return True

        # Update page
        print(f"\n📤 Updating page...")
        try:
            result = self.update_page(page_id, title, translated_content, version, space_key)
            new_version = result['version']['number']
            print(f"✅ Page updated successfully! (version {version} → {new_version})")
            print(f"🔗 {self.base_url}{result['_links']['webui']}")
            return True
        except Exception as e:
            print(f"❌ Error updating page: {e}")
            return False


def create_translator(args, skip_translation_init: bool = False) -> "ConfluenceTranslator":
    """Create translator from args."""
    config_path = getattr(args, 'config', '../config.yaml')
    model = getattr(args, 'model', 'gpt-4o')
    backend = getattr(args, 'backend', 'openai')

    if getattr(args, 'url', None) and getattr(args, 'username', None) and getattr(args, 'token', None):
        # Use direct auth
        return ConfluenceTranslator(
            base_url=args.url,
            username=args.username,
            api_token=args.token,
            use_bearer_token=getattr(args, 'bearer', False),
            translation_backend=backend,
            model=model,
            skip_translation_init=skip_translation_init
        )
    else:
        # Use config file
        if not os.path.isabs(config_path):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, config_path)

        config = SyncConfig.from_yaml(config_path)
        print(f"📄 Using config: {config_path}")
        return ConfluenceTranslator.from_config(
            config,
            translation_backend=backend,
            model=model,
            skip_translation_init=skip_translation_init
        )


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Confluence page translator - download, translate, and upload wiki pages'
    )
    parser.add_argument('--config', default='../config.yaml', help='Path to config file')

    # Direct auth options
    parser.add_argument('--url', help='Confluence base URL')
    parser.add_argument('--username', help='Confluence username')
    parser.add_argument('--token', help='Confluence API token')
    parser.add_argument('--bearer', action='store_true', help='Use Bearer token auth')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download page for manual translation')
    download_parser.add_argument('page', help='Page ID or URL')
    download_parser.add_argument('-o', '--output', help='Output file path')

    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload translated content')
    upload_parser.add_argument('file', help='Translated content file (.html)')
    upload_parser.add_argument('--metadata', help='Metadata file (.json)')

    # Translate command (auto translate)
    translate_parser = subparsers.add_parser('translate', help='Auto-translate page')
    translate_parser.add_argument('page', help='Page ID or URL')
    translate_parser.add_argument('--source', default='zh', help='Source language code (default: zh)')
    translate_parser.add_argument('--target', default='en', help='Target language code (default: en)')
    translate_parser.add_argument(
        '--backend', '-b',
        default='tencent',
        choices=list_backends(),
        help='Translation backend (default: tencent)'
    )
    translate_parser.add_argument('--model', default='gpt-4o', help='Model (for OpenAI backend)')
    translate_parser.add_argument('--dry-run', action='store_true', help='Preview only, do not update page')

    args = parser.parse_args()

    # Default to showing help if no command
    if not args.command:
        parser.print_help()
        print("\n📖 Examples:")
        print("   # Download page for manual translation")
        print("   confluence-sync translate download 1035120878")
        print("   confluence-sync translate download 'https://wiki.../pages/123/Title'")
        print("")
        print("   # Upload translated content")
        print("   confluence-sync translate upload page_123.html")
        print("")
        print("   # Auto-translate with Tencent TMT (requires TENCENT_SECRET_ID, TENCENT_SECRET_KEY)")
        print("   confluence-sync translate translate 1035120878 --backend tencent --dry-run")
        print("")
        print("   # Auto-translate with OpenAI (requires OPENAI_API_KEY)")
        print("   confluence-sync translate translate 1035120878 --backend openai --dry-run")
        print("")
        print("   # Available backends:", ', '.join(list_backends()))
        sys.exit(0)

    # Create translator
    skip_init = args.command in ['download', 'upload']
    try:
        translator = create_translator(args, skip_translation_init=skip_init)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing: {e}")
        sys.exit(1)

    # Execute command
    if args.command == 'download':
        success = translator.download_page(args.page, args.output)
    elif args.command == 'upload':
        success = translator.upload_page(args.file, args.metadata)
    elif args.command == 'translate':
        source = getattr(args, 'source', 'zh')
        target = getattr(args, 'target', 'en')
        print(f"\n🚀 Starting translation ({source} → {target})...")
        success = translator.translate_page(
            args.page,
            source_lang=source,
            target_lang=target,
            dry_run=args.dry_run
        )
    else:
        parser.print_help()
        sys.exit(0)

    if success:
        print("\n🎉 Done!")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
