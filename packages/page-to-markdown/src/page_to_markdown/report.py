"""Confidence and metadata reporting for page-to-markdown extraction."""

from collections import Counter
from datetime import datetime, timezone
import re

from page_to_markdown.select import (
    STRIP_TAGS,
    _DomBuilder,
    _DomNode,
    _find_all,
    _find_first,
    _text_density,
)


BLOCK_TAGS = frozenset(
    ["div", "section", "p", "ul", "ol", "table", "blockquote", "pre"]
)
HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6"])
SHORT_OUTPUT_CHARS = 40
SCRIPT_TAG_MINIMUM = 3
NAVIGATION_LINK_MINIMUM = 3
NAVIGATION_TEXT_RATIO = 0.6
NAVIGATION_PARAGRAPH_CHARS = 80
WHITESPACE_PATTERN = re.compile(r"\s+")


class _CountingDomBuilder(_DomBuilder):
    """Build the shared lightweight DOM while counting source elements."""

    def __init__(self):
        super().__init__()
        self.tag_counts = Counter()

    def handle_starttag(self, tag, attrs):
        self.tag_counts[tag.lower()] += 1
        super().handle_starttag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self.tag_counts[tag.lower()] += 1
        super().handle_startendtag(tag, attrs)


def build_report(
    raw_html: str,
    selected_html: str,
    markdown: str,
    source: str | None,
) -> str:
    """Build an advisory confidence report from raw and selected HTML."""
    raw_builder = _parse(raw_html)
    selected_builder = _parse(selected_html)
    selected_root = _content_root_label(raw_builder.root)
    removed_elements = _removed_elements(
        raw_builder.tag_counts, selected_builder.tag_counts
    )
    selected_text = _normalise_text(selected_builder.root.full_text)
    links = _find_all(selected_builder.root, lambda node: node.tag == "a")
    link_text_length = sum(len(_normalise_text(node.full_text)) for node in links)
    paragraph_text_length = sum(
        len(_normalise_text(node.full_text))
        for node in _find_all(selected_builder.root, lambda item: item.tag == "p")
    )

    reasons = []
    if _is_js_app_shell(raw_builder):
        reasons.append(
            "JS app shell detected: the body is nearly empty despite multiple "
            "script tags; use web-audit render before converting"
        )
    if not raw_builder.tag_counts:
        reasons.append("non-HTML response detected: no HTML elements were found")
    if len(markdown.strip()) < SHORT_OUTPUT_CHARS:
        reasons.append(
            "converted Markdown is empty or very short "
            f"({len(markdown.strip())} characters)"
        )
    if _is_mostly_navigation(
        len(selected_text), len(links), link_text_length, paragraph_text_length
    ):
        reasons.append(
            "mostly-navigation content detected: links contain most of the "
            "selected text and there is little paragraph prose"
        )

    if reasons:
        verdict = "low-confidence"
    elif len(markdown.strip()) < 120 or selected_root in {
        "body",
        "density-fallback",
        "root",
    }:
        verdict = "medium-confidence"
    else:
        verdict = "high-confidence"

    removed_total = sum(removed_elements.values())
    removed_summary = ", ".join(
        f"{tag}={count}" for tag, count in sorted(removed_elements.items())
    )
    if not removed_summary:
        removed_summary = "none"

    lines = [
        f"source: {source or 'stdin'}",
        f"selected-content-root: {selected_root}",
        f"removed-elements: {removed_summary} (total={removed_total})",
        f"links: {len(links)}",
        f"code-blocks: {selected_builder.tag_counts.get('pre', 0)}",
        f"verdict: {verdict}",
    ]
    lines.extend(f"reason: {reason}" for reason in reasons)
    return "\n".join(lines)


def build_metadata(
    raw_html: str,
    selected_html: str,
    source: str | None,
) -> dict[str, str | None]:
    """Build JSON-serialisable metadata for an extracted document."""
    return {
        "title": _extract_title(raw_html, selected_html),
        "url": source if _is_http_source(source) else None,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _parse(html: str) -> _CountingDomBuilder:
    """Parse HTML using the selector's shared DOM implementation."""
    builder = _CountingDomBuilder()
    builder.feed(html if isinstance(html, str) else "")
    builder.close()
    return builder


def _content_root_label(root: _DomNode) -> str:
    """Mirror select_content's root-selection labels without changing it."""
    if _find_first(root, lambda node: node.tag == "main"):
        return "main"
    if _find_first(root, lambda node: node.tag == "article"):
        return "article"
    if _find_first(
        root, lambda node: node.attrs.get("role", "").lower() == "main"
    ):
        return "role=main"

    candidates = _find_all(root, lambda node: node.tag in BLOCK_TAGS)
    if candidates:
        best = max(candidates, key=lambda node: _text_density(node))
        if best.text_length > 0:
            return "density-fallback"

    if _find_first(root, lambda node: node.tag == "body"):
        return "body"
    return "root"


def _removed_elements(
    raw_counts: Counter,
    selected_counts: Counter,
) -> dict[str, int]:
    """Count stripped elements that are absent from the selected HTML."""
    return {
        tag: raw_counts[tag] - selected_counts.get(tag, 0)
        for tag in STRIP_TAGS
        if raw_counts[tag] > selected_counts.get(tag, 0)
    }


def _is_js_app_shell(builder: _CountingDomBuilder) -> bool:
    """Detect script-heavy HTML with almost no readable body text."""
    body = _find_first(builder.root, lambda node: node.tag == "body")
    body_text = body.full_text if body else builder.root.full_text
    return (
        builder.tag_counts.get("script", 0) >= SCRIPT_TAG_MINIMUM
        and len(_normalise_text(body_text)) < SHORT_OUTPUT_CHARS
    )


def _is_mostly_navigation(
    selected_text_length: int,
    link_count: int,
    link_text_length: int,
    paragraph_text_length: int,
) -> bool:
    """Identify link-heavy selections with too little paragraph prose."""
    if link_count < NAVIGATION_LINK_MINIMUM or not selected_text_length:
        return False

    # Three links, 60% link text, and fewer than 80 prose characters catches
    # navigation blocks without penalising normal short articles.
    return (
        link_text_length / selected_text_length >= NAVIGATION_TEXT_RATIO
        and paragraph_text_length < NAVIGATION_PARAGRAPH_CHARS
    )


def _extract_title(raw_html: str, selected_html: str) -> str | None:
    """Extract the raw title, falling back to the first selected heading."""
    raw_root = _parse(raw_html).root
    title = _find_first(raw_root, lambda node: node.tag == "title")
    title_text = _normalise_text(title.full_text) if title else ""
    if title_text:
        return title_text

    selected_root = _parse(selected_html).root
    heading = _find_first(selected_root, lambda node: node.tag in HEADING_TAGS)
    heading_text = _normalise_text(heading.full_text) if heading else ""
    return heading_text or None


def _normalise_text(text: str) -> str:
    """Collapse HTML whitespace for report measurements and metadata."""
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _is_http_source(source: str | None) -> bool:
    """Return whether a source is an HTTP(S) URL."""
    return bool(source and source.startswith(("http://", "https://")))
