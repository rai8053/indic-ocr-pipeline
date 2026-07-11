"""General-purpose helper utilities for the pipeline."""

from __future__ import annotations

import base64
import re as _re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Terminal output (Rich-aware)
# ---------------------------------------------------------------------------

try:
    from rich.console import Console as _Console

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

_console: Optional[_Console] = None


def _get_console() -> Optional[_Console]:
    """Lazy-init the shared Rich console instance."""
    global _console
    if _console is None and _HAS_RICH:
        from rich.console import Console

        _console = Console()
    return _console


def info(text: str = "") -> None:
    """Print an info-level message (bold blue with Rich, plain otherwise)."""
    c = _get_console()
    if c:
        c.print(text, style="bold blue")
    else:
        print(text)


def ok(text: str = "") -> None:
    """Print a success message (bold green)."""
    c = _get_console()
    if c:
        c.print(text, style="bold green")
    else:
        print(text)


def warn(text: str = "") -> None:
    """Print a warning message (bold yellow)."""
    c = _get_console()
    if c:
        c.print(text, style="bold yellow")
    else:
        print(text)


def err(text: str = "") -> None:
    """Print an error message (bold red)."""
    c = _get_console()
    if c:
        c.print(text, style="bold red")
    else:
        print(text)


def bold(text: str = "") -> None:
    """Print bold text."""
    c = _get_console()
    if c:
        c.print(text, style="bold")
    else:
        print(text)


def raw(text: str = "") -> None:
    """Print text with inline Rich markup (e.g. ``[bold]text[/bold]``)."""
    c = _get_console()
    if c:
        c.print(text)
    else:
        cleaned = _re.sub(r"\[/?\w+\]", "", text)
        print(cleaned)


def rule(title: str = "", char: str = "=") -> None:
    """Print a horizontal rule with an optional title."""
    line = char * 52
    c = _get_console()
    if c:
        if title:
            c.print(f"\n[blue]{line}[/blue]")
            c.print(f"      [bold]{title}[/bold]")
            c.print(f"[blue]{line}[/blue]")
        else:
            c.print(f"[blue]{line}[/blue]")
    else:
        if title:
            print(f"\n{line}")
            print(f"           {title}")
            print(f"{line}")
        else:
            print(line)


def banner(title: str = "", subtitle: str = "") -> None:
    """Print a banner with title and optional subtitle."""
    line = "-" * 52
    c = _get_console()
    if c:
        c.print(f"\n[blue]+{line}+[/blue]")
        c.print(f"[blue]|[/blue]  [bold]{title}[/bold]")
        if subtitle:
            c.print(f"[blue]|[/blue]  [blue]{subtitle}[/blue]")
        c.print(f"[blue]|[/blue]")
        c.print(f"[blue]+{line}+[/blue]")
    else:
        print(f"\n{'=' * 52}")
        print(f"\n  {title}")
        if subtitle:
            print(f"  {subtitle}")
        print(f"\n{'=' * 52}")


def panel(title: str = "", content: str = "", border: str = "blue") -> None:
    """Print a bordered panel with title and content."""
    line = "-" * 52
    c = _get_console()
    if c:
        c.print(f"[blue]+{line}+[/blue]")
        if title:
            c.print(f"[blue]|[/blue]  [bold]{title}[/bold]")
            c.print(f"[blue]|[/blue]")
        if content:
            for part in content.strip().split("\n"):
                c.print(f"[blue]|[/blue]  {part}")
        c.print(f"[blue]+{line}+[/blue]")
    else:
        if title:
            print(f"\n{'=' * 52}")
            print(f"  {title}")
            print(f"{'=' * 52}")
        if content:
            print(content)


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------


def image_to_base64(image_path: Path) -> str:
    """Read an image file and return its contents as a base64-encoded string.

    Args:
        image_path: Path to the image file (JPEG or PNG).

    Returns:
        Base64-encoded string of the raw image bytes.
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
