"""Command-line entry point for capturing worktree review feedback."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import shutil
import subprocess
import sys

from review_feedback import style
from review_feedback.draft import (
	Draft,
	DraftEntry,
	DraftError,
	DraftStore,
	NoActiveDraftError,
	append_entry,
	load_active,
	remove_entry,
	repository_fingerprint,
	resolve_store,
	retire_active,
	save_active,
	validate_entries,
)
from review_feedback.git_selection import SelectionError, resolve_selection


class ClipboardError(RuntimeError):
	"""Report that macOS clipboard access is unavailable or failed."""


class CliError(RuntimeError):
	"""Report an interactive command failure with a recovery action."""


def build_parser() -> argparse.ArgumentParser:
	"""Build the review-feedback command parser."""
	parser = argparse.ArgumentParser(
		prog="review-feedback",
		description=(
			"Capture copied Git worktree selections and comments as review feedback."
		),
	)
	commands = parser.add_subparsers(dest="command", required=True)

	commands.add_parser(
		"add",
		help="capture the current macOS clipboard selection and one comment",
	)

	show_parser = commands.add_parser(
		"show",
		help="display entries in the active review draft",
	)
	show_parser.add_argument(
		"--json",
		action="store_true",
		help="write active entries as JSON",
	)

	remove_parser = commands.add_parser(
		"remove",
		help="remove one entry without renumbering the remaining entries",
	)
	remove_parser.add_argument(
		"number", type=int, help="Stable entry number to remove."
	)

	preview_parser = commands.add_parser(
		"preview",
		help="validate the active draft and write its packet",
	)
	preview_parser.add_argument(
		"--copy",
		action="store_true",
		help="also copy the packet to the macOS clipboard",
	)

	finish_parser = commands.add_parser(
		"finish",
		help="write the packet and retire the active draft to Trash",
	)
	finish_parser.add_argument(
		"--copy",
		action="store_true",
		help="also copy the packet to the macOS clipboard",
	)

	commands.add_parser(
		"clear",
		help="retire the active draft to Trash without writing a packet",
	)

	return parser


def main(argv: list[str] | None = None) -> int:
	"""Run a review-feedback command and report recoverable failures."""
	args = build_parser().parse_args(argv)

	try:
		return _run_command(args)
	except (ClipboardError, CliError, DraftError, SelectionError) as error:
		sys.stderr.write(style.status("failed", "Error", str(error)) + "\n")
		return 2


def _run_command(args: argparse.Namespace) -> int:
	"""Dispatch parsed arguments to one review-feedback command."""
	if args.command == "add":
		return _add()
	if args.command == "show":
		return _show(args.json)
	if args.command == "remove":
		return _remove(args.number)
	if args.command == "preview":
		return _preview(args.copy)
	if args.command == "finish":
		return _finish(args.copy)
	if args.command == "clear":
		return _clear()

	raise CliError(f"unknown command: {args.command}")


def _add() -> int:
	"""Capture clipboard text, prompt for a comment, and append one entry."""
	store = resolve_store()
	selection = read_clipboard()
	comment = _prompt_comment()
	location = resolve_selection(selection, store.root)
	fingerprint = repository_fingerprint(store.root)
	draft = load_active(store) or Draft([])
	entry = append_entry(draft, location, selection, comment, fingerprint)
	save_active(store, draft)

	sys.stdout.write(
		style.status(
			"success",
			"Added",
			f"entry {entry.number} for {_location_text(entry)}",
		)
		+ "\n"
	)
	return 0


def _show(as_json: bool) -> int:
	"""Display active entries without reading or displaying source excerpts."""
	store = resolve_store()
	draft = load_active(store)
	entries = [] if draft is None else [asdict(entry) for entry in draft.entries]

	if as_json:
		payload = {
			"active": draft is not None,
			"entries": entries,
			"repository": str(store.root),
		}
		sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
		return 0

	if draft is None:
		sys.stdout.write(style.status("info", "No active draft") + "\n")
		return 0

	sys.stdout.write(
		style.status("success", "Active draft", f"{len(draft.entries)} entries") + "\n"
	)
	for entry in draft.entries:
		sys.stdout.write(
			style.row(
				f"Entry {entry.number}",
				f"{_location_text(entry)}: {entry.comment}",
			)
			+ "\n"
		)

	return 0


def _remove(number: int) -> int:
	"""Remove one stable-numbered entry from the active draft."""
	store = resolve_store()
	draft = _require_active(store)
	removed = remove_entry(draft, number)
	save_active(store, draft)
	sys.stdout.write(
		style.status("success", "Removed", f"entry {removed.number}") + "\n"
	)
	return 0


def _preview(copy_packet: bool) -> int:
	"""Validate and write the active packet without changing draft state."""
	store = resolve_store()
	draft = _require_active(store)
	validate_entries(store, draft)
	packet = _render_packet(draft)
	_write_packet(packet, copy_packet)
	return 0


def _finish(copy_packet: bool) -> int:
	"""Validate, write, and retire the active packet after output succeeds."""
	store = resolve_store()
	draft = _require_active(store)
	validate_entries(store, draft)
	packet = _render_packet(draft)
	_write_packet(packet, copy_packet)
	retire_active(store, "finished")
	return 0


def _clear() -> int:
	"""Retire an abandoned active draft without producing a packet."""
	store = resolve_store()
	retired_path = retire_active(store, "abandoned")
	sys.stdout.write(
		style.status("success", "Cleared", f"draft moved to {retired_path}") + "\n"
	)
	return 0


def read_clipboard() -> str:
	"""Read text from the macOS clipboard using pbpaste."""
	if sys.platform != "darwin":
		raise ClipboardError(
			"clipboard unavailable: this version supports macOS only; "
			"copy the selection manually on macOS and run `review-feedback add`"
		)

	if shutil.which("pbpaste") is None:
		raise ClipboardError(
			"clipboard unavailable: pbpaste was not found on PATH; "
			"copy the selection manually and run `review-feedback add`"
		)

	try:
		result = subprocess.run(
			["pbpaste"],
			capture_output=True,
			check=True,
		)
	except FileNotFoundError as error:
		raise ClipboardError(
			"clipboard unavailable: pbpaste was not found on PATH; "
			"copy the selection manually and run `review-feedback add`"
		) from error
	except OSError as error:
		raise ClipboardError(
			f"clipboard read failed: {error}; copy the selection manually and "
			"run `review-feedback add`"
		) from error
	except subprocess.CalledProcessError as error:
		raise ClipboardError(
			f"clipboard read failed: pbpaste exited with status {error.returncode}; "
			"copy the selection manually and run `review-feedback add`"
		) from error

	try:
		selection = result.stdout.decode("utf-8")
	except UnicodeDecodeError as error:
		raise ClipboardError(
			"clipboard content is not readable UTF-8; copy plain text and "
			"run `review-feedback add`"
		) from error

	if selection == "":
		raise ClipboardError(
			"clipboard is empty; copy one source selection and run `review-feedback add`"
		)

	return selection


def copy_to_clipboard(text: str) -> None:
	"""Copy generated packet text to the macOS clipboard using pbcopy."""
	if sys.platform != "darwin":
		raise ClipboardError(
			"clipboard unavailable: this version supports macOS only; "
			"save the packet from standard output instead"
		)

	if shutil.which("pbcopy") is None:
		raise ClipboardError(
			"clipboard unavailable: pbcopy was not found on PATH; "
			"save the packet from standard output instead"
		)

	try:
		subprocess.run(["pbcopy"], input=text, text=True, check=True)
	except FileNotFoundError as error:
		raise ClipboardError(
			"clipboard unavailable: pbcopy was not found on PATH; "
			"save the packet from standard output instead"
		) from error
	except OSError as error:
		raise ClipboardError(
			f"clipboard copy failed: {error}; save the packet from standard output "
			"instead"
		) from error
	except subprocess.CalledProcessError as error:
		raise ClipboardError(
			f"clipboard copy failed: pbcopy exited with status {error.returncode}; "
			"save the packet from standard output instead"
		) from error


def _prompt_comment() -> str:
	"""Prompt for one non-empty review comment."""
	try:
		comment = input("Comment: ")
	except EOFError as error:
		raise CliError(
			"comment prompt closed; run `review-feedback add` and enter one comment"
		) from error

	if not comment.strip():
		raise CliError("comment cannot be empty; run `review-feedback add` again")

	return comment


def _require_active(store: DraftStore) -> Draft:
	"""Load an active draft or report the command needed to create one."""
	draft = load_active(store)
	if draft is None:
		raise NoActiveDraftError(
			"no active review draft exists; run `review-feedback add` first"
		)

	return draft


def _write_packet(packet: str, copy_packet: bool) -> None:
	"""Write a packet and optionally copy it before any draft retirement."""
	try:
		sys.stdout.write(packet)
		sys.stdout.flush()
	except (BrokenPipeError, OSError) as error:
		raise CliError(f"could not write packet: {error}") from error

	if copy_packet:
		copy_to_clipboard(packet)


def _render_packet(draft: Draft) -> str:
	"""Render the minimal packet used until the full renderer chunk lands."""
	lines = ["# Review feedback", ""]

	for entry in draft.entries:
		side = f" ({entry.side})" if entry.side != "current" else ""
		comment_lines = entry.comment.splitlines() or [entry.comment]
		lines.append(
			f"{entry.number}. `{_location_text(entry)}`{side}: {comment_lines[0]}"
		)
		lines.extend(f"   {line}" for line in comment_lines[1:])

	return "\n".join(lines) + "\n"


def _location_text(entry: DraftEntry) -> str:
	"""Format a persisted repository-relative location."""
	return (
		f"{entry.path}:{entry.start_line}:{entry.start_column}-"
		f"{entry.end_line}:{entry.end_column}"
	)


if __name__ == "__main__":
	raise SystemExit(main())
