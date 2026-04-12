#!/usr/bin/env python3
"""
Mermaid Diagram Renderer

Renders Mermaid diagram code to PNG/SVG images using mermaid-cli (mmdc).
"""

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MermaidConfig:
    """Mermaid rendering configuration."""
    output_format: str = "png"  # "png" or "svg"
    theme: str = "default"  # "default", "dark", "forest", "neutral"
    background_color: str = "white"
    width: int = 800
    height: int = 600
    scale: int = 2  # For higher resolution PNG
    timeout_seconds: int = 30


@dataclass
class RenderResult:
    """Result of rendering a Mermaid diagram."""
    success: bool
    image_path: Optional[Path] = None
    error: Optional[str] = None


class MermaidRenderer:
    """
    Renders Mermaid diagrams to images using mermaid-cli.

    Requires mermaid-cli to be installed:
        npm install -g @mermaid-js/mermaid-cli
    """

    def __init__(
        self,
        config: Optional[MermaidConfig] = None,
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize the renderer.

        Args:
            config: Rendering configuration
            output_dir: Directory to save rendered images (uses temp dir if None)
        """
        self.config = config or MermaidConfig()
        self.output_dir = output_dir or Path(tempfile.mkdtemp(prefix="mermaid_"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._mmdc_path: Optional[str] = None

    def is_available(self) -> bool:
        """Check if mermaid-cli (mmdc) is available."""
        return self._find_mmdc() is not None

    def _find_mmdc(self) -> Optional[str]:
        """Find the mmdc executable."""
        if self._mmdc_path:
            return self._mmdc_path

        # Try to find mmdc in PATH
        mmdc = shutil.which("mmdc")
        if mmdc:
            self._mmdc_path = mmdc
            return mmdc

        # Try common npm global paths
        common_paths = [
            Path(__file__).resolve().parent.parent / ".bin" / "mmdc",
            Path(__file__).resolve().parent.parent / ".tools" / "node_modules" / ".bin" / "mmdc",
            Path.home() / ".npm-global" / "bin" / "mmdc",
            Path.home() / "node_modules" / ".bin" / "mmdc",
            Path("/usr/local/bin/mmdc"),
        ]
        for path in common_paths:
            if path.exists():
                self._mmdc_path = str(path)
                return self._mmdc_path

        return None

    def render(self, mermaid_code: str, filename: Optional[str] = None) -> RenderResult:
        """
        Render Mermaid code to an image.

        Args:
            mermaid_code: Mermaid diagram code
            filename: Output filename (auto-generated if None)

        Returns:
            RenderResult with path to rendered image or error
        """
        mmdc = self._find_mmdc()
        if not mmdc:
            return RenderResult(
                success=False,
                error="mermaid-cli (mmdc) not found. Install with: npm install -g @mermaid-js/mermaid-cli"
            )

        # Generate filename from content hash if not provided
        if not filename:
            content_hash = hashlib.md5(mermaid_code.encode()).hexdigest()[:8]
            filename = f"mermaid_{content_hash}.{self.config.output_format}"

        output_path = self.output_dir / filename

        # Write mermaid code to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.mmd', delete=False, encoding='utf-8'
        ) as f:
            f.write(mermaid_code)
            input_file = f.name

        try:
            # Build mmdc command
            cmd = [
                mmdc,
                "-i", input_file,
                "-o", str(output_path),
                "-t", self.config.theme,
                "-b", self.config.background_color,
                "-w", str(self.config.width),
                "-H", str(self.config.height),
            ]

            if self.config.output_format == "png":
                cmd.extend(["-s", str(self.config.scale)])

            # Run mmdc
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )

            if result.returncode != 0:
                return RenderResult(
                    success=False,
                    error=f"mmdc failed: {result.stderr or result.stdout}"
                )

            if not output_path.exists():
                return RenderResult(
                    success=False,
                    error=f"Output file not created: {output_path}"
                )

            return RenderResult(success=True, image_path=output_path)

        except subprocess.TimeoutExpired:
            return RenderResult(
                success=False,
                error=f"Rendering timed out after {self.config.timeout_seconds}s"
            )
        except Exception as e:
            return RenderResult(success=False, error=str(e))
        finally:
            # Clean up temp input file
            Path(input_file).unlink(missing_ok=True)

    def cleanup(self) -> None:
        """Clean up temporary files."""
        if self.output_dir.exists() and str(self.output_dir).startswith(tempfile.gettempdir()):
            shutil.rmtree(self.output_dir, ignore_errors=True)
