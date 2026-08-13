"""Turn a review draft into a Markdown comment packet."""

from review_feedback.draft import Draft, DraftEntry, location_text


def render_packet(draft: Draft) -> str:
	"""Build the full Markdown packet from a draft's entries, or an empty string when there are none."""
	if not draft.entries:
		return ""

	entries = [_render_entry(entry) for entry in draft.entries]
	return "\n\n".join(entries) + "\n"


def _render_entry(entry: DraftEntry) -> str:
	"""Format one draft entry as a numbered heading with its location and comment."""
	location = location_text(entry)
	removed_suffix = " (removed at HEAD)" if entry.side == "removed" else ""
	heading = f"### {entry.number}. `{location}`{removed_suffix}"
	return f"{heading}\n\n{entry.comment}"
