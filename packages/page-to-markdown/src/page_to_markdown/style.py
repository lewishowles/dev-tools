"""Render page-to-markdown CLI output through the repository's cli-style binary."""

from pathlib import Path

from page_to_markdown._cli_style import (
    hint as render_hint,
    render as render_generic,
    span as render_span,
    status as render_status,
)


def _binary_path() -> str:
    """Return the repository-local cli-style binary path."""
    return str(Path(__file__).resolve().parents[4] / "node_modules" / ".bin" / "cli-style")


def status(result_type: str, label: str = "", detail: str = "") -> str:
    """Render a status line using the repository-local cli-style binary."""
    return render_status(
        result_type,
        label,
        detail,
        binary=_binary_path(),
    )


def hint(message: str) -> str:
    """Render a hint line using the repository-local cli-style binary."""
    return render_hint(message, binary=_binary_path())


def row(label: str, value: str, result: str = "", label_width: int | None = None) -> str:
    """Render a labelled row using the repository-local cli-style binary.

    label_width aligns a group of rows into columns, matching cli-style's own
    convention (see its gallery's "Rows" section) since row() renders one line
    at a time with no shared state between calls.
    """
    data = {"label": label, "value": value, "result": result}

    if label_width is not None:
        data["labelWidth"] = label_width

    return render_generic("row", data, binary=_binary_path())


def span(value: str, tone: str = "info") -> str:
    """Render an inline span using the repository-local cli-style binary."""
    return render_span(value, tone, binary=_binary_path())
