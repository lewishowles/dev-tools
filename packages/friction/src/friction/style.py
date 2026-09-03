"""Render friction CLI output through cli-style when it is installed."""

from collections.abc import Callable

from ._cli_style import CliStyleNotFoundError
from ._cli_style import row as render_row
from ._cli_style import span as render_span
from ._cli_style import status as render_status


def _render_or_plain(
	styled_renderer: Callable[[], str],
	plain_renderer: Callable[[], str],
) -> str:
	"""Render with cli-style, falling back to plain terminal text when absent."""
	try:
		return styled_renderer()
	except CliStyleNotFoundError:
		return plain_renderer()


def span(value: str, tone: str = "info") -> str:
	"""Render one inline value through cli-style or return its plain text."""
	return _render_or_plain(
		lambda: render_span(value, tone),
		lambda: value,
	)


def row(label: str, value: str, result: str = "") -> str:
	"""Render one labelled value through cli-style or a plain equivalent."""
	return _render_or_plain(
		lambda: render_row(label, value, result),
		lambda: f"{label}  {value}",
	)


def status(result: str, label: str, detail: str) -> str:
	"""Render one status line through cli-style or a plain equivalent."""
	return _render_or_plain(
		lambda: render_status(result, label, detail),
		lambda: f"{label} {detail}".rstrip(),
	)
