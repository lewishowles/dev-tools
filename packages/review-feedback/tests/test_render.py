from review_feedback.draft import Draft, DraftEntry
from review_feedback.render import render_packet


def make_entry(
	number: int,
	path: str,
	side: str,
	comment: str,
) -> DraftEntry:
	"""Build a draft entry with stable coordinates for renderer tests."""
	return DraftEntry(
		number=number,
		path=path,
		side=side,
		start_line=2,
		start_column=3,
		end_line=4,
		end_column=8,
		selection_hash="selection-hash",
		repository_fingerprint="repository-fingerprint",
		comment=comment,
		old_path="old_name.py",
		new_path="new_name.py",
	)


def test_render_packet_uses_schema_for_current_and_removed_entries() -> None:
	draft = Draft(
		[
			make_entry(1, "new_name.py", "current", "Check this current code."),
			make_entry(3, "old_name.py", "removed", "Check this removed code."),
		]
	)

	packet = render_packet(draft)

	assert packet == (
		"### 1. `new_name.py:2:3-4:8`\n\n"
		"Check this current code.\n\n"
		"### 3. `old_name.py:2:3-4:8` (removed at HEAD)\n\n"
		"Check this removed code.\n"
	)
	assert "# Review feedback" not in packet
	assert "> Check" not in packet


def test_render_packet_keeps_multiline_comments_plain() -> None:
	entry = make_entry(4, "review.py", "current", "First line\nSecond line")

	packet = render_packet(Draft([entry]))

	assert packet == ("### 4. `review.py:2:3-4:8`\n\nFirst line\nSecond line\n")


def test_render_packet_returns_empty_body_for_empty_draft() -> None:
	assert render_packet(Draft([])) == ""
