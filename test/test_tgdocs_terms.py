"""Offline tests for `tgdocs.py terms`: the developer terms page is replaced by small fake pages
shaped like telegram.org/tos/bot-developers.

Run as test_tgdocs.py says.
"""

from __future__ import annotations

import contextlib
import html
import io
import re
import sys

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

import tgdocs


def run_main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["tgdocs.py", *argv])
    return tgdocs.main()


ANCHOR = '<a class="anchor" name="x" href="#x"><i class="anchor-icon"></i></a>'


def terms_page(body: str, title: str = tgdocs.TERMS_TITLE) -> str:
    """Shaped like telegram.org/tos/bot-developers: a language menu and a footer with headings of
    their own around the content block."""
    return (
        f"<html><head><title>{title}</title></head><body>"
        '<ul class="nav"><li class="chosen"><a href="?setln=en">English</a></li><li><a href="?setln=ru">Русский</a></li></ul>'
        f'<div id="dev_page_content_wrap"><h1 id="dev_page_title">{title}</h1>'
        f'<div id="dev_page_content"><p>Bots and Mini Apps are third party applications.</p>{body}</div></div>'
        '<div class="footer_column"><h5><a href="/press">Press</a></h5></div></body></html>'
    )


# The real page sets 6.2, 6.2.6 and 6.3 in the same <h4>: only the numbers say where a clause ends.
TERMS_BODY = (
    f"<h3>{ANCHOR}6. Monetization</h3>"
    f"<h4>{ANCHOR}6.2. Telegram Stars</h4><p>Stars are a currency.</p>"
    f"<h4>{ANCHOR}6.2.6. Enabling Topics in Private Chats</h4>"
    '<p>Developers may use <a href="https://t.me/botfather">@BotFather</a> to enable topics.</p>'
    "<p>All subsequent Telegram Stars purchases carried out within that TPA shall be subject to a "
    "non-refundable fee of 15%, which will be automatically withheld.<br>For clarity, the TPA&#39;s fee ends.</p>"
    f"<h4>{ANCHOR}6.2.7. Expiration</h4><p>Stars are valid for 3 years.</p>"
    "<blockquote><p>Stars may not become available for up to 21 days.</p></blockquote>"
    f"<h5>{ANCHOR}6.2.7.1. Receiving Rewards</h5><p>Rewards arrive later.</p>"
    f"<h4>{ANCHOR}6.3. Account Management</h4>"
    "<ul><li>(d) the following use cases are forbidden<ul><li>Fake giveaways.</li><li>Fake airdrops.</li></ul></li></ul>"
)


@pytest.fixture
def terms(monkeypatch):
    pages = {tgdocs.TERMS_URL: terms_page(TERMS_BODY)}
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: pages[path])
    return pages


def test_terms_section_prints_one_clause_verbatim(terms, monkeypatch, capsys):
    assert run_main(monkeypatch, "terms", "--section", "6.2.6") == 0
    out = capsys.readouterr().out
    assert out.startswith("### 6.2.6. Enabling Topics in Private Chats\n")
    assert "Developers may use @BotFather to enable topics." in out
    # <br> separates the items of a clause, as (a)…(d) in 4.2 of the real page: it stays a line break.
    assert "non-refundable fee of 15%, which will be automatically withheld.\nFor clarity, the TPA's fee ends." in out
    assert "6.2.7" not in out and "Press" not in out
    assert f"(Source: {tgdocs.TERMS_TITLE}, {tgdocs.TERMS_URL})" in out


def test_terms_section_ends_by_clause_number_not_by_heading_tag(terms, monkeypatch, capsys):
    assert run_main(monkeypatch, "terms", "--section", "6.2") == 0
    out = capsys.readouterr().out
    for inside in ("## 6.2. Telegram Stars", "### 6.2.6.", "### 6.2.7. Expiration", "21 days", "#### 6.2.7.1. Receiving Rewards"):
        assert inside in out
    assert "6.3" not in out


def test_terms_toc_lists_the_clauses_and_nothing_around_them(terms, monkeypatch, capsys):
    assert run_main(monkeypatch, "terms", "--toc") == 0
    out = capsys.readouterr().out
    assert "    - 6.2.6. Enabling Topics in Private Chats" in out
    assert "Press" not in out and "English" not in out and tgdocs.TERMS_TITLE + "\n" not in out.split("(Source")[0]


def test_terms_keep_a_nested_list_item_apart_from_its_parent_and_indented(terms, monkeypatch, capsys):
    # The real 5.2 has an "(i)" nested in "(d)" and another "(i)" of its own: depth tells them apart.
    assert run_main(monkeypatch, "terms", "--section", "6.3") == 0
    lines = capsys.readouterr().out.splitlines()
    assert "- (d) the following use cases are forbidden" in lines
    assert "  - Fake giveaways." in lines and "  - Fake airdrops." in lines


# Layouts today's page does not use but HTML allows: text outside <p>, a nested <div>, a script.
LOOSE_TERMS_BODY = (
    f"<h3>{ANCHOR}5. Code of Conduct</h3>"
    "<ul><li>(d) forbidden use cases<ul><li>(i) MLM schemes</li></ul>unless approved in writing.</li></ul>"
    "<blockquote>A bare note in a quote.</blockquote>"
    '<div class="note"><p>Inside a nested div.</p>Loose text in the div.</div>'
    "<script>var tracking = 1;</script>"
    f"<h3>{ANCHOR}6. Monetization</h3><p>After the div.</p>"
    "<h3>Annex</h3><p>Not part of clause 6.</p>"
)


def test_terms_keep_text_that_sits_outside_paragraphs(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: terms_page(LOOSE_TERMS_BODY))
    assert run_main(monkeypatch, "terms", "--section", "5") == 0
    out = capsys.readouterr().out
    for kept in ("- (d) forbidden use cases", "  - (i) MLM schemes", "unless approved in writing.", "A bare note in a quote.",
                 "Inside a nested div.", "Loose text in the div."):
        assert kept in out
    assert "tracking" not in out and "After the div" not in out


def test_terms_an_unnumbered_heading_does_not_fall_inside_a_clause(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: terms_page(LOOSE_TERMS_BODY))
    assert run_main(monkeypatch, "terms", "--section", "6") == 0
    out = capsys.readouterr().out
    assert "After the div." in out and "Annex" not in out and "Press" not in out


@pytest.mark.parametrize("broken", [
    terms_page(TERMS_BODY).split("automatically withheld")[0],  # a download or cache file cut short
    # Two unclosed <div>s outlast the wrapper's closing tag, and the footer would join the last clause.
    terms_page(TERMS_BODY.replace("<h4>", "<div><div><h4>", 1)),
])
def test_terms_refuse_a_page_whose_content_block_does_not_close(monkeypatch, capsys, broken):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: broken)
    assert run_main(monkeypatch, "terms", "--section", "6.2.6") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "content block" in captured.err and "--fresh" in captured.err


def test_terms_gone_from_their_address_say_so(monkeypatch, capsys):
    def gone(path: str, fresh: bool, allow_stale: bool) -> str:
        raise tgdocs.PageNotFound(f"{path} does not exist (404). Try `search` or `index` to find the page.")

    monkeypatch.setattr(tgdocs, "fetch", gone)
    assert run_main(monkeypatch, "terms", "--toc") == 1
    err = capsys.readouterr().err
    assert "developer terms" in err and "https://telegram.org/tos" in err and "search" not in err


def test_page_sends_the_developer_terms_to_the_terms_command(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: terms_page(TERMS_BODY))
    assert run_main(monkeypatch, "page", tgdocs.TERMS_URL) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "tgdocs.py terms" in captured.err


def test_terms_refuse_a_page_that_is_another_document(monkeypatch, capsys):
    # What telegram.org answers for `bot-developers.md`: the general Terms of Service, with a 200.
    page = terms_page("<h3>1. Общие положения</h3><p>Текст.</p>", title="Пользовательское соглашение Telegram")
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: page)
    assert run_main(monkeypatch, "terms", "--section", "6.2.6") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "'Пользовательское соглашение Telegram', not the Telegram Bot Platform Developer Terms" in captured.err


def test_terms_are_requested_at_their_own_address_without_md(monkeypatch, tmp_path):
    requested: list[str] = []

    def answer(request, timeout):
        requested.append(request.full_url)
        return contextlib.nullcontext(io.BytesIO(terms_page(TERMS_BODY).encode("utf-8")))

    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answer)
    tgdocs.fetch(tgdocs.TERMS_URL, fresh=False, allow_stale=False)
    assert requested == ["https://telegram.org/tos/bot-developers"]


# Text a clause can carry: any printable character, including the ones HTML escapes and the ones
# Markdown reads as structure.
CLAUSE_TEXT = st.text(st.characters(blacklist_categories=("Cs", "Cc")) | st.sampled_from("\n\t<>&'\"#-"), max_size=30)


@st.composite
def numbered_terms(draw):
    """(clauses in document order as (number, tag, title, paragraphs), the number asked for).
    Tags are drawn independently of depth, as on the real page; up to 12 top-level clauses, so
    that 1 and 11 both exist."""
    clauses = []

    def add(prefix: str, depth: int) -> None:
        count = draw(st.integers(1, 12)) if depth == 1 else draw(st.integers(0, 2))
        for n in range(1, count + 1):
            number = f"{prefix}{n}"
            clauses.append((number, draw(st.sampled_from(["h3", "h4", "h5"])), draw(CLAUSE_TEXT), draw(st.lists(CLAUSE_TEXT, max_size=2))))
            if depth < 3:
                add(number + ".", depth + 1)

    add("", 1)
    return clauses, draw(st.sampled_from([number for number, _, _, _ in clauses]))


def render_terms(clauses) -> str:
    return terms_page("".join(
        f"<{tag}>{ANCHOR}{number}. {html.escape(title)}</{tag}>" + "".join(f"<p>{html.escape(text)}</p>" for text in paragraphs)
        for number, tag, title, paragraphs in clauses
    ))


REAL_PAGE_SHAPE = ([("6", "h3", "Monetization", []), ("6.2", "h4", "Stars", ["a"]), ("6.2.6", "h4", "Topics", ["15%"]), ("6.3", "h4", "Accounts", ["b"])], "6.2")


@given(numbered_terms())
@example(REAL_PAGE_SHAPE)
@example(([("1", "h3", "One", ["# looks like a heading"]), ("1.1", "h4", "Sub", ["x"]), ("11", "h3", "Eleven", ["y"])], "1"))
@example(([("1", "h3", "One", ["``` looks like code"]), ("1.1", "h4", "Sub", ["x"]), ("2", "h3", "Two", ["y"])], "1"))
@example(([("1", "h3", "One", ["- # looks like a list heading"]), ("1.1", "h4", "Sub", ["x"]), ("2", "h3", "Two", ["y"])], "1"))
def test_a_terms_section_is_exactly_its_clause_and_subclauses(document):
    clauses, wanted = document
    expected = []
    for number, _, title, paragraphs in clauses:
        if number == wanted or number.startswith(wanted + "."):
            expected.append("#" * len(number.split(".")) + " " + " ".join(f"{number}. {title}".split()))
            for text in (" ".join(p.split()) for p in paragraphs):
                if text:
                    # Text that Markdown reads as a heading or a code fence is printed escaped.
                    expected.append(("\\" if re.match(r"(?:[*+-] )?#{1,6}\s|`{3}|~{3}", text) else "") + text)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tgdocs.print_section(tgdocs.terms_markdown(render_terms(clauses)), wanted, "the developer terms", by_clause_number=True)
    assert out.getvalue().strip() == "\n\n".join(expected)
