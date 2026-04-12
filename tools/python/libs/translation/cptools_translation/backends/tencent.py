#!/usr/bin/env python3
"""
Tencent Cloud Machine Translation (TMT) backend.

Environment variables:
- TENCENT_SECRET_ID: Tencent Cloud Secret ID (required)
- TENCENT_SECRET_KEY: Tencent Cloud Secret Key (required)
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from .base import TranslationBackend


class TencentTMTBackend(TranslationBackend):
    """
    Tencent Cloud Machine Translation (TMT) backend.
    
    Advantages:
    - Fast and cost-effective
    - Good for simple text translation
    
    Args:
        secret_id: Tencent Cloud Secret ID (or set TENCENT_SECRET_ID env var)
        secret_key: Tencent Cloud Secret Key (or set TENCENT_SECRET_KEY env var)
        region: API region (default: ap-guangzhou)
    """
    
    # Language code mapping
    LANG_MAP = {
        'zh': 'zh',
        'zh-CN': 'zh',
        'zh-TW': 'zh-TW',
        'en': 'en',
        'ja': 'ja',
        'ko': 'ko',
        'auto': 'auto',
    }
    
    def __init__(
        self,
        secret_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "ap-guangzhou"
    ):
        self.secret_id = secret_id or os.environ.get('TENCENT_SECRET_ID')
        self.secret_key = secret_key or os.environ.get('TENCENT_SECRET_KEY')
        self.region = region
        self.service = "tmt"
        self.host = "tmt.tencentcloudapi.com"
        self.endpoint = f"https://{self.host}"
        
        if not self.secret_id or not self.secret_key:
            raise ValueError(
                "Tencent Cloud credentials required. "
                "Set TENCENT_SECRET_ID and TENCENT_SECRET_KEY environment variables."
            )
    
    @property
    def name(self) -> str:
        return "Tencent TMT"
    
    @property
    def max_chunk_size(self) -> int:
        return 5000  # TMT limit is 6000 chars, use 5000 for safety
    
    def _sign(self, key: bytes, msg: str) -> bytes:
        """HMAC-SHA256 signing."""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_auth_header(self, payload: str, timestamp: int) -> dict:
        """Generate TC3 signature for Tencent Cloud API."""
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        # Step 1: Build canonical request
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{self.host}\nx-tc-action:texttranslate\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (
            f"{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n"
            f"{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        )

        # Step 2: Build string to sign
        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"

        # Step 3: Calculate signature
        secret_date = self._sign(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # Step 4: Build authorization header
        authorization = (
            f"{algorithm} Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": self.host,
            "X-TC-Action": "TextTranslate",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2018-03-21",
            "X-TC-Region": self.region,
        }

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate using Tencent Cloud TMT API."""
        # Map language codes
        source = self.LANG_MAP.get(source_lang, source_lang)
        target = self.LANG_MAP.get(target_lang, target_lang)

        payload = json.dumps({
            "SourceText": text,
            "Source": source,
            "Target": target,
            "ProjectId": 0
        })

        timestamp = int(time.time())
        headers = self._get_auth_header(payload, timestamp)

        response = requests.post(self.endpoint, headers=headers, data=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        if "Response" in result:
            if "Error" in result["Response"]:
                error = result["Response"]["Error"]
                raise Exception(f"TMT Error: {error.get('Code')} - {error.get('Message')}")
            return result["Response"].get("TargetText", "")

        raise Exception(f"Unexpected TMT response: {result}")

