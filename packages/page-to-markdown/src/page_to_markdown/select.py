"""Content selection for page-to-markdown.

Strips page chrome (script, style, nav, header, footer, etc.) and selects
the main content region using deterministic rules: main, then article,
then [role=main], then highest-text-density fallback.

Uses only the standard library (html.parser) to preserve nested markup
for later Markdown conversion.
"""

from html.parser import HTMLParser

# Elements to strip entirely (content and tags).
STRIP_TAGS = frozenset(
    ["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]
)

# Void (self-closing) elements that never have children.
VOID_TAGS = frozenset(
    [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    ]
)


class _DomNode:
    """A lightweight DOM node built by _DomBuilder."""

    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs) if attrs else {}
        self.children = []
        self.parent = parent
        self.text = ""

    def add_text(self, text):
        node = _DomNode("#text", parent=self)
        node.text = text
        self.children.append(node)

    @property
    def full_text(self):
        """All direct and descendant text, concatenated."""
        parts = [self.text]
        for child in self.children:
            parts.append(child.full_text)
        return "".join(parts)

    @property
    def text_length(self):
        """Length of all descendant text, excluding whitespace."""
        return len(self.full_text.strip())

    @property
    def tag_count(self):
        """Count of all descendant element nodes (not #text)."""
        return sum(
            1 + c.tag_count for c in self.children if c.tag != "#text"
        )


class _DomBuilder(HTMLParser):
    """Builds a lightweight DOM tree from HTML using html.parser."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _DomNode("#root")
        self._stack = [self.root]
        # Track whether we're inside a stripped element at each depth.
        self._strip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        # If inside a stripped element, ignore everything.
        if self._strip_depth > 0:
            if tag not in VOID_TAGS:
                self._strip_depth += 1
            return

        if tag in STRIP_TAGS:
            self._strip_depth = 1
            return

        node = _DomNode(tag, attrs, self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        """Handle self-closing tags like <img/>."""
        tag = tag.lower()
        if self._strip_depth > 0:
            return
        if tag in STRIP_TAGS:
            return
        node = _DomNode(tag, attrs, self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._strip_depth > 0:
            if tag not in VOID_TAGS:
                self._strip_depth -= 1
            return

        # Pop stack until we find the matching tag (handles implicit closes).
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._strip_depth > 0:
            return
        self._stack[-1].add_text(data)


def _serialize(node):
    """Serialize a DOM node back to HTML, preserving nested markup."""
    parts = []
    for child in node.children:
        if child.tag == "#text":
            parts.append(child.text)
            continue

        attrs_str = "".join(
            f' {k}' if v is None else f' {k}="{v}"'
            for k, v in child.attrs.items()
        )

        if child.tag in VOID_TAGS:
            parts.append(f"<{child.tag}{attrs_str}>")
        else:
            inner = _serialize(child)
            parts.append(f"<{child.tag}{attrs_str}>{inner}</{child.tag}>")

    return "".join(parts)


def _find_first(root, predicate):
    """Depth-first search for the first node matching predicate."""
    for child in root.children:
        if predicate(child):
            return child
        result = _find_first(child, predicate)
        if result is not None:
            return result
    return None


def _find_all(root, predicate, results=None):
    """Find all nodes matching predicate, depth-first."""
    if results is None:
        results = []
    for child in root.children:
        if predicate(child):
            results.append(child)
        _find_all(child, predicate, results)
    return results


def _text_density(node):
    """Text-to-tag ratio for a node. Higher means more text-dense."""
    tc = node.tag_count
    if tc == 0:
        return 0.0
    return node.text_length / tc


def select_content(html):
    """Select the main content region from an HTML string.

    Returns the selected region as an HTML string with page chrome stripped.
    Rules, in order:
    1. First <main> element.
    2. First <article> element.
    3. First element with role="main".
    4. Highest-text-density block-level element as fallback.
    5. The body (or root) if nothing better is found.
    """
    builder = _DomBuilder()
    builder.feed(html)
    builder.close()
    root = builder.root

    # 1. <main>
    main = _find_first(root, lambda n: n.tag == "main")
    if main:
        return _serialize(main)

    # 2. <article>
    article = _find_first(root, lambda n: n.tag == "article")
    if article:
        return _serialize(article)

    # 3. [role=main]
    role_main = _find_first(
        root, lambda n: n.attrs.get("role", "").lower() == "main"
    )
    if role_main:
        return _serialize(role_main)

    # 4. Highest-text-density block-level element
    block_tags = frozenset(
        ["div", "section", "p", "ul", "ol", "table", "blockquote", "pre"]
    )
    candidates = _find_all(root, lambda n: n.tag in block_tags)
    if candidates:
        best = max(candidates, key=lambda n: _text_density(n))
        if best.text_length > 0:
            return _serialize(best)

    # 5. Fallback: serialize the body or the whole root
    body = _find_first(root, lambda n: n.tag == "body")
    if body:
        return _serialize(body)
    return _serialize(root)
