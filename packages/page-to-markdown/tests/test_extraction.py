from pathlib import Path

import pytest

from page_to_markdown.convert import convert_to_markdown
from page_to_markdown.fetch import read_file
from page_to_markdown.report import build_metadata, build_report
from page_to_markdown.select import select_content


# Keep extraction tests entirely on checked-in fixture files.
FIXTURES = Path(__file__).parents[1] / "fixtures"


def load_fixture(name: str) -> str:
    """Read a local HTML fixture through the production file loader."""
    return read_file(FIXTURES / name)


def extract_fixture(name: str, base_url: str | None = None) -> tuple[str, str, str]:
    """Run the local fixture through reading, selection, and conversion."""
    raw_html = load_fixture(name)
    selected_html = select_content(raw_html)
    markdown = convert_to_markdown(selected_html, base_url=base_url)
    return raw_html, selected_html, markdown


@pytest.mark.parametrize(
    "fixture_name",
    [
        "simple.html",
        "blog-with-chrome.html",
        "docs-page-with-code.html",
        "table-heavy.html",
        "js-app-shell.html",
        "relative-links.html",
        "short-page.html",
    ],
)
def test_every_fixture_runs_through_local_extraction_pipeline(fixture_name: str) -> None:
    raw_html, selected_html, _ = extract_fixture(fixture_name)

    assert raw_html
    assert selected_html


def test_simple_fixture_preserves_full_body_content() -> None:
    _, _, markdown = extract_fixture("simple.html")

    assert markdown == "# Hello\n\nThis is a test page.\n"


def test_blog_fixture_removes_page_chrome_and_reports_selection() -> None:
    raw_html, selected_html, markdown = extract_fixture("blog-with-chrome.html")
    report = build_report(raw_html, selected_html, markdown, "blog-with-chrome.html")

    assert "Understanding content selection" in markdown
    assert "Welcome to my blog" not in markdown
    assert "Subscribe to our newsletter" not in markdown
    assert "Copyright 2024 My Blog" not in markdown
    assert "selected-content-root: main" in report
    assert "removed-elements:" in report
    assert "verdict: high-confidence" in report


def test_docs_fixture_matches_checked_in_markdown() -> None:
    _, selected_html, markdown = extract_fixture("docs-page-with-code.html")
    expected_markdown = read_file(FIXTURES / "docs-page-with-code.expected.md")

    assert selected_html
    assert markdown == expected_markdown


def test_table_fixture_matches_checked_in_markdown() -> None:
    _, selected_html, markdown = extract_fixture("table-heavy.html")
    expected_markdown = read_file(FIXTURES / "table-heavy.expected.md")

    assert selected_html
    assert markdown == expected_markdown


def test_relative_links_resolve_against_the_document_url() -> None:
    _, _, markdown = extract_fixture(
        "relative-links.html", base_url="https://example.com/docs/page.html"
    )

    assert (
        "[getting started guide](https://example.com/guide/getting-started.html)"
        in markdown
    )
    assert "[reference](https://example.com/reference)" in markdown


@pytest.mark.parametrize(
    ("fixture_name", "reason"),
    [
        ("js-app-shell.html", "JS app shell detected"),
        ("short-page.html", "converted Markdown is empty or very short"),
    ],
)
def test_low_confidence_fixtures_include_actionable_report_reasons(
    fixture_name: str, reason: str
) -> None:
    raw_html, selected_html, markdown = extract_fixture(fixture_name)
    report = build_report(raw_html, selected_html, markdown, fixture_name)

    assert "verdict: low-confidence" in report
    assert f"reason: {reason}" in report


def test_local_fixture_metadata_contains_title_without_inventing_a_url() -> None:
    raw_html, selected_html, _ = extract_fixture("simple.html")
    metadata = build_metadata(raw_html, selected_html, "simple.html")

    assert metadata["title"] == "Simple fixture"
    assert metadata["url"] is None
    assert metadata["timestamp"]
