"""CLI entry point for page-to-markdown.

Handles input from a URL, local file, or stdin, selects the main content
region, converts it to Markdown, and writes it to stdout or a file.
"""

import argparse
import sys

from page_to_markdown.convert import convert_to_markdown
from page_to_markdown.fetch import FetchError, fetch_url, read_file
from page_to_markdown.select import select_content


def build_parser():
    parser = argparse.ArgumentParser(
        prog="page-to-markdown",
        description="Convert a URL, file, or piped HTML into compact Markdown.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="URL or path to an HTML file. Mutually exclusive with --stdin.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read HTML from stdin. Mutually exclusive with a source argument.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write output to this path instead of stdout.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.stdin and args.source:
        parser.error("--stdin cannot be combined with a source argument")

    if not args.stdin and not args.source:
        parser.error("provide a URL/file argument or use --stdin")

    try:
        if args.stdin:
            content = sys.stdin.read()
        elif args.source.startswith(("http://", "https://")):
            content = fetch_url(args.source)
        else:
            content = read_file(args.source)
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    content = select_content(content)
    base_url = (
        args.source
        if args.source and args.source.startswith(("http://", "https://"))
        else None
    )
    content = convert_to_markdown(content, base_url=base_url)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            print(f"error: could not write to {args.output}: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
