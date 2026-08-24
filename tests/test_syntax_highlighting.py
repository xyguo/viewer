"""Tests for static code-block syntax highlighting."""

from __future__ import annotations

from book_viewer.syntax_highlighting import highlight_code_blocks


def test_plain_code_blocks_receive_line_wrappers() -> None:
    rendered = highlight_code_blocks("<pre><code>first line\n\nthird line</code></pre>")

    assert rendered == (
        '<pre><code><span class="code-line">first line</span>\n'
        '<span class="code-line">&#8203;</span>\n'
        '<span class="code-line">third line</span></code></pre>'
    )


def test_pandoc_highlighted_code_is_not_rewritten() -> None:
    rendered = (
        '<pre class="sourceCode c"><code class="sourceCode c">'
        '<span id="cb1-1"><span class="dt">int</span> value;</span>'
        "</code></pre>"
    )

    assert highlight_code_blocks(rendered) == rendered


def test_pandoc_html_tokens_are_preserved_for_static_highlighting() -> None:
    rendered = (
        '<pre class="sourceCode html"><code class="sourceCode html">'
        '<span id="cb1-1"><span class="dt">&lt;</span><span class="kw">section</span>'
        '<span class="ot"> class</span><span class="op">=</span>'
        '<span class="st">&quot;note&quot;</span><span class="dt">&gt;</span></span>\n'
        '<span id="cb1-2"><span class="co">&lt;!-- comment --&gt;</span></span>'
        "</code></pre>"
    )

    assert highlight_code_blocks(rendered) == rendered


def test_lean_code_blocks_receive_static_highlighting_and_line_wrappers() -> None:
    rendered = highlight_code_blocks(
        '<pre class="lean"><code>def add (a b : Nat) : Nat := a + b\n\n'
        "-- Evaluate the result.\n#eval add 2 3</code></pre>"
    )

    assert rendered.count('<span class="code-line">') == 4
    assert '<span class="kw">def</span> <span class="fu">add</span>' in rendered
    assert '<span class="dt">Nat</span>' in rendered
    assert '<span class="op">:=</span>' in rendered
    assert '<span class="code-line">&#8203;</span>' in rendered
    assert '<span class="co">-- Evaluate the result.</span>' in rendered
    assert '<span class="pp">#eval</span> add <span class="dv">2</span>' in rendered


def test_lean4_highlighting_handles_nested_comments_literals_and_escaping() -> None:
    rendered = highlight_code_blocks(
        '<pre class="lean4"><code>/- outer\n  /- nested -/\n-/\n'
        "def less (value : Nat) := value &lt; 2 &amp;&amp; true\n"
        '#check "text"</code></pre>'
    )

    assert rendered.count('<span class="co">') == 3
    assert '<span class="fu">less</span>' in rendered
    assert '<span class="op">&lt;</span>' in rendered
    assert '<span class="op">&amp;&amp;</span>' in rendered
    assert '<span class="cn">true</span>' in rendered
    assert '<span class="st">&quot;text&quot;</span>' in rendered
