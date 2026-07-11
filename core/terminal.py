import re as _re

try:
    from rich.console import Console as _Console
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

_console = None


def _get():
    global _console
    if _console is None and _HAS_RICH:
        _console = _Console()
    return _console


def info(text=""):
    c = _get()
    if c:
        c.print(text, style="bold blue")
    else:
        print(text)


def ok(text=""):
    c = _get()
    if c:
        c.print(text, style="bold green")
    else:
        print(text)


def warn(text=""):
    c = _get()
    if c:
        c.print(text, style="bold yellow")
    else:
        print(text)


def err(text=""):
    c = _get()
    if c:
        c.print(text, style="bold red")
    else:
        print(text)


def bold(text=""):
    c = _get()
    if c:
        c.print(text, style="bold")
    else:
        print(text)


def rule(title="", char="="):
    line = char * 52
    c = _get()
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


def banner(title="", subtitle=""):
    line = "-" * 52
    c = _get()
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


def raw(text=""):
    """Print with inline Rich markup (e.g. [bold]text[/bold], [red]text[/red])."""
    c = _get()
    if c:
        c.print(text)
    else:
        cleaned = _re.sub(r"\[/?\w+\]", "", text)
        print(cleaned)


def panel(title="", content="", border="blue"):
    line = "-" * 52
    c = _get()
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
