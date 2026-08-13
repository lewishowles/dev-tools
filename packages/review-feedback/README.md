# review-feedback

`review-feedback` records comments against exact locations in a Git worktree and renders one Markdown packet for an agent or review workflow. It keeps copied source text out of the draft after the location is matched.

## Requirements

- macOS for clipboard input and `--copy`
- Python 3.11 or newer
- `uv`
- A Git worktree

## Install

From the repository root, install the local package as a tool:

```sh
uv tool install ./packages/review-feedback
```

## Usage

1. In your Git tool of choice, select the source text you want to review and copy it.
2. In a terminal opened in the same repository, run `review-feedback add` and enter the comment when prompted.
3. Repeat the first two steps for each comment.
4. Review the packet without changing the draft:

```sh
review-feedback preview
```

5. When the packet is ready, copy it and retire the draft:

```sh
review-feedback finish --copy
```

Use `review-feedback preview --copy` if you want to copy the packet while keeping the draft active. A successful `finish` moves the draft to trash, so the next `add` starts a new review.

## Recover from a failed selection

The copied text must identify one location. When the command reports a failure, no entry is added:

- **Not found:** copy the exact text again from the current Git view, including enough surrounding context, then run `review-feedback add`.
- **Ambiguous:** the text appears in more than one location. Copy more surrounding context and run `review-feedback add` again.
- **Spans both sides:** the selection combines current and removed content. Copy one side at a time and add separate comments.
- **Stale during preview or finish:** the file changed after capture. Remove the affected entry with `review-feedback remove <number>`, then copy the current text and add it again.

The packet uses the working-tree path and coordinates for current content. Removed content is marked `(removed at HEAD)` and uses its `HEAD` path and coordinates.

## Clipboard limitation

Clipboard access uses macOS `pbpaste` and `pbcopy`. `review-feedback add` and the `--copy` flags need those commands on `PATH`; on another platform, or when either command is unavailable, copy the selection or save the packet from standard output manually. The matching and rendering commands do not require clipboard output when you use `preview` without `--copy`.
