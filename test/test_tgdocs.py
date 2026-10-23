"""Offline tests for tgdocs.py: the docs are replaced by small fake pages.

Run from the repository root (test/conftest.py makes the skill's scripts importable):
  uv run --with pytest --with hypothesis python -m pytest test
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import io
import os
import re
import socket
import ssl
import sys
import time

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

import tgdocs

API_INDEX = """# Telegram Bot API

- [sendMessage](/bots/api/methods/sendmessage.md): send text messages.
- [editEphemeralMessageText](/bots/api/methods/editephemeralmessagetext.md): edit an ephemeral text or rich message.

All types are listed at [Available types](/bots/api/types.md#available-types), see also [Types](/bots/api/types.md).
Formatting is described at [Formatting options](/bots/api/formatting.md).

### Rich messages

Rich message methods, types and formatting rules are documented at [Rich messages](/bots/api/rich-messages.md).
"""

PAGES = {
    "bots/api": API_INDEX,
    "bots/api/types": (
        "- [Message](/bots/api/types/message.md): This object represents a message.\n"
        "- [EphemeralMessageParameters](/bots/api/types/ephemeralmessageparameters.md)\n"
    ),
    "bots/api/formatting": "# Formatting options\n\nNo index lines here.\n",
    "bots/api/rich-messages": (
        "- [sendRichMessage](/bots/api/methods/sendrichmessage.md): send rich messages.\n"
        "- [RichBlockTable](/bots/api/types/richblocktable.md): A table, corresponding to the HTML tag `<table>`.\n"
        "- [Message](/bots/api/types/message.md): This object represents a message.\n"
        "- [sendMessageXL](/bots/api/methods/sendmessagexl.md): send a large thing.\n"
    ),
    "bots/api/methods/getunlistedthing": "# getUnlistedThing\n\n> Part of the Telegram Bot API.\n\nUse this method to get a thing.\n",
    "bots/api/methods/sendmessagex": "# sendMessageX\n\n> Part of the Telegram Bot API.\n\nUse this method to send a thing.\n",
    "bots/api-changelog": (
        "### 2026\n\n#### August 24, 2026\n\n**Bot API 10.3**\n\n- Added the class RichMessageButton.\n\n"
        "#### July 14, 2026\n\n**Bot API 10.2**\n\n- Added the parameter receiver_user_id.\n\n"
        "#### April 3, 2026\n\n**Bot API 9.6**\n\n- Added something older.\n"
    ),
}


@pytest.fixture
def docs(monkeypatch):
    requested: list[str] = []

    def fake_fetch(path: str, fresh: bool, allow_stale: bool) -> str:
        requested.append(path)
        if path not in PAGES:
            raise tgdocs.PageNotFound(f"{path} does not exist (404).")
        return PAGES[path]

    monkeypatch.setattr(tgdocs, "fetch", fake_fetch)
    return requested


def search(term: str) -> None:
    tgdocs.cmd_search(argparse.Namespace(term=term, fresh=False, allow_stale=False))


def test_search_finds_methods_and_types_listed_only_on_a_linked_subpage(docs, capsys):
    search("sendRichMessage")
    search("RichBlockTable")
    out = capsys.readouterr().out
    assert "method sendRichMessage — send rich messages." in out
    assert "type   RichBlockTable — A table" in out


def test_search_lists_an_item_once_even_when_two_pages_list_it(docs, capsys):
    search("Message")
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("type   Message ")]
    assert len(lines) == 1


def test_search_falls_back_to_the_exact_page_when_no_index_lists_the_name(docs, capsys):
    search("getUnlistedThing")
    out = capsys.readouterr().out
    assert "method getUnlistedThing" in out
    assert "not listed in the indexes" in out


def test_search_without_any_match_points_to_history_for_parameters(docs, capsys):
    search("receiver_user_id")
    out = capsys.readouterr().out
    assert "No method or type" in out
    assert "history receiver_user_id" in out


def test_search_for_a_phrase_does_not_probe_a_page_named_after_it(docs, capsys):
    search("zzz qqq")
    assert "No method or type" in capsys.readouterr().out
    assert not any(path.startswith("bots/api/methods/") or path.startswith("bots/api/types/") for path in docs)


def test_search_tries_the_exact_page_when_the_hits_are_only_partial(docs, capsys):
    search("sendMessageX")  # the indexes list sendMessageXL, not sendMessageX
    out = capsys.readouterr().out
    assert "method sendMessageXL" in out
    assert "method sendMessageX — not listed in the indexes" in out


def test_search_does_not_hide_a_network_failure_behind_the_fallback(monkeypatch):
    def failing_fetch(path: str, fresh: bool, allow_stale: bool) -> str:
        if path in PAGES and path != "bots/api/methods/getunlistedthing":
            return PAGES[path]
        raise tgdocs.DocsError(f"cannot reach {path}: timed out.")

    monkeypatch.setattr(tgdocs, "fetch", failing_fetch)
    with pytest.raises(tgdocs.DocsError, match="could not check.*cannot reach"):
        search("nothingLikeThis")


def test_search_does_not_hide_a_network_failure_on_a_linked_page(monkeypatch):
    def failing_fetch(path: str, fresh: bool, allow_stale: bool) -> str:
        if path == "bots/api/rich-messages":
            raise tgdocs.DocsError(f"cannot reach {path}: timed out.")
        return PAGES[path]

    monkeypatch.setattr(tgdocs, "fetch", failing_fetch)
    with pytest.raises(tgdocs.DocsError, match="cannot reach"):
        search("RichBlockTable")


def test_search_reads_the_type_index_even_if_the_main_index_stops_linking_it(monkeypatch, capsys):
    pages = dict(PAGES, **{"bots/api": "- [sendMessage](/bots/api/methods/sendmessage.md): send text messages.\n"})
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: pages[path])
    search("EphemeralMessageParameters")
    assert "type   EphemeralMessageParameters" in capsys.readouterr().out


def test_search_skips_a_linked_page_that_is_gone_and_says_so(monkeypatch, capsys):
    pages = {path: text for path, text in PAGES.items() if path != "bots/api/formatting"}

    def fetch_without_formatting(path: str, fresh: bool, allow_stale: bool) -> str:
        if path not in pages:
            raise tgdocs.PageNotFound(f"{path} does not exist (404).")
        return pages[path]

    monkeypatch.setattr(tgdocs, "fetch", fetch_without_formatting)
    search("RichBlockTable")
    captured = capsys.readouterr()
    assert "type   RichBlockTable" in captured.out
    assert "bots/api/formatting" in captured.err


def run_main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["tgdocs.py", *argv])
    return tgdocs.main()


def test_changes_since_prints_only_newer_versions(docs, monkeypatch, capsys):
    assert run_main(monkeypatch, "changes", "--since", "10.2") == 0
    out = capsys.readouterr().out
    assert "Bot API 10.3" in out
    assert "Bot API 10.2" not in out and "Bot API 9.6" not in out


@pytest.mark.parametrize("bad", ["ten", "10.x", "v10.3", ""])
def test_changes_rejects_a_version_that_is_not_a_number(docs, monkeypatch, capsys, bad):
    with pytest.raises(SystemExit) as exit_info:
        run_main(monkeypatch, "changes", "--since", bad)
    assert exit_info.value.code == 2
    assert "is not a Bot API version" in capsys.readouterr().err


def test_a_missing_page_is_remembered_like_a_page_is(monkeypatch, tmp_path):
    calls: list[str] = []

    def not_found(request, timeout):
        calls.append(request.full_url)
        raise tgdocs.urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", not_found)
    for _ in range(2):
        with pytest.raises(tgdocs.PageNotFound):
            tgdocs.fetch("bots/api/methods/nosuchmethod", fresh=False, allow_stale=False)
    assert len(calls) == 1
    with pytest.raises(tgdocs.PageNotFound):
        tgdocs.fetch("bots/api/methods/nosuchmethod", fresh=True, allow_stale=False)
    assert len(calls) == 2


def cp1252_stdout(monkeypatch):
    """What a Windows pipe gives Python by default: the ANSI code page, not UTF-8."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    return stream


def test_pages_with_emoji_print_through_a_windows_code_page(monkeypatch):
    pages = dict(PAGES, **{"bots/api/methods/senddice": "# sendDice\n\nEmoji: 🎲, 🎯, 🏀 — and → arrows.\n"})
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: pages[path])
    stream = cp1252_stdout(monkeypatch)
    assert run_main(monkeypatch, "method", "sendDice") == 0
    stream.flush()
    assert "🎲, 🎯, 🏀 — and → arrows" in stream.buffer.getvalue().decode("utf-8")


def test_an_untrusted_certificate_is_named_with_the_fix(monkeypatch, tmp_path):
    def untrusted(request, timeout):
        raise tgdocs.urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))

    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", untrusted)
    with pytest.raises(tgdocs.DocsError, match="Install Certificates"):
        tgdocs.fetch("bots/api-changelog", fresh=False, allow_stale=False)


GUIDE = """# Mini Apps

## Recent changes

#### June 11, 2026

Added fullscreen tweaks.

#### May 8, 2026

Added storage.

## Implementing Mini Apps

### Keyboard button Mini Apps

Text.
"""


@pytest.mark.parametrize("wanted, starts, excludes", [
    ("Recent changes", "## Recent changes", "Implementing"),  # exact; ends at the next heading of its level
    ("2026", "#### June 11, 2026", "May 8"),  # a year is a substring like any other, not a clause number
    ("implementing", "## Implementing Mini Apps", "Recent"),  # deeper headings stay inside
])
def test_page_section_matches_headings_as_before(monkeypatch, capsys, wanted, starts, excludes):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: GUIDE)
    assert run_main(monkeypatch, "page", "bots/webapps", "--section", wanted) == 0
    out = capsys.readouterr().out
    assert out.startswith(starts) and excludes not in out
    if wanted == "implementing":
        assert "### Keyboard button Mini Apps" in out


def test_page_toc_indents_by_heading_level(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: GUIDE)
    assert run_main(monkeypatch, "page", "bots/webapps", "--toc") == 0
    assert capsys.readouterr().out.splitlines()[:3] == ["- Mini Apps", "  - Recent changes", "      - June 11, 2026"]


# Shaped like bots/serverless: shell comments inside code blocks start with "#" too.
SERVERLESS = """# Telegram Serverless

## Getting started

```bash
# Recommended — create a project with the CLI installed into it:
npm create @tgcloud/bot example_bot

# Or install the CLI globally:
npm i -g tgcloud
```

Then link your bot.

~~~
## not a heading either
```
still code: a ``` line does not close a ~~~ block
~~~

## Projects and modules

Text.
"""


def test_page_toc_skips_comment_lines_inside_code_blocks(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: SERVERLESS)
    assert run_main(monkeypatch, "page", "bots/serverless", "--toc") == 0
    assert capsys.readouterr().out.splitlines() == ["- Telegram Serverless", "  - Getting started", "  - Projects and modules"]


WEBHOOKS = """### The longer version

* #### A domain name
Setting a webhook needs a URL for us to post to.

* #### An open port
Ports currently supported for Webhooks: 443, 80, 88, 8443.

* #### Always SSL/TLS
Unencrypted connections are not supported.

### Getting it right
"""


def test_page_section_finds_a_heading_that_opens_a_list_item(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: WEBHOOKS)
    assert run_main(monkeypatch, "page", "bots/webhooks", "--section", "An open port") == 0
    assert capsys.readouterr().out.strip() == "* #### An open port\nPorts currently supported for Webhooks: 443, 80, 88, 8443."


def test_page_section_keeps_its_code_blocks_whole(monkeypatch, capsys):
    monkeypatch.setattr(tgdocs, "fetch", lambda path, fresh, allow_stale: SERVERLESS)
    assert run_main(monkeypatch, "page", "bots/serverless", "--section", "Getting started") == 0
    out = capsys.readouterr().out
    assert "npm i -g tgcloud" in out and "Then link your bot." in out and "still code" in out
    assert "Projects and modules" not in out


HEADING_TITLE = st.text(st.sampled_from("abcXYZ019 .-#`~:"), min_size=1, max_size=12).filter(lambda t: t.strip())
CODE_LINE = st.text(st.sampled_from("ab #`~-"), max_size=10).map(lambda t: t.rstrip())


@st.composite
def markdown_with_code(draw):
    """(Markdown text, its real headings as (level, title)): headings, paragraphs and fenced code
    blocks whose lines read like headings ("# comment") or like other fences; the last block may
    be left unclosed, as Markdown allows."""
    lines, headings = [], []
    for _ in range(draw(st.integers(1, 8))):
        kind = draw(st.sampled_from(["heading", "paragraph", "code"]))
        if kind == "heading":
            level, title = draw(st.integers(1, 6)), draw(HEADING_TITLE).strip()
            # bots/webhooks opens list items with a heading: "* #### An open port".
            lines.append(draw(st.sampled_from(["", "", "* ", "- "])) + "#" * level + " " + title)
            headings.append((level, title))
        elif kind == "paragraph":
            lines.append(draw(st.text(st.sampled_from("abc 019.,"), min_size=1, max_size=20)).strip() or "text")
        else:
            char, length = draw(st.sampled_from("`~")), draw(st.integers(3, 5))
            fence = " " * draw(st.integers(0, 3)) + char * length
            closes = re.compile(r" {0,3}" + re.escape(char) + "{" + str(length) + r",}\s*$")
            body = [line for line in draw(st.lists(CODE_LINE, max_size=5)) if not closes.match(line)]
            lines += [fence + draw(st.sampled_from(["", "bash", "js"]))] + body
            if not draw(st.integers(0, 3)):
                break  # one block in four is left unclosed: it runs to the end of the text
            closing = " " * draw(st.integers(0, 3)) + char * (length + draw(st.integers(0, 2)))
            lines.append(closing + draw(st.sampled_from(["", "", " ", "\t"])))  # bots/webhooks has "``` "
    return "\n".join(lines) + "\n", headings


@given(markdown_with_code())
@example(("```bash\n# Recommended\n```\n## Real\n", [(2, "Real")]))
@example(("~~~\n```\n# still code\n~~~\n# Out\n", [(1, "Out")]))
@example(("````\n```\n# still code\n````\n# Out\n", [(1, "Out")]))
@example(("```js\n# never closed\n", []))
@example(("```x``` is inline code, not a fence\n# Real\n", [(1, "Real")]))
@example(("```\n``` with text after it does not close\n# still code\n```\n# Out\n", [(1, "Out")]))
@example(("```\n# code\n``` \n# Out\n", [(1, "Out")]))
@example(("* #### An open port\n- # a heading too\n```\n* # in code\n```\n", [(4, "An open port"), (1, "a heading too")]))
def test_headings_are_found_only_outside_code_blocks(document):
    text, headings = document
    assert [(level, title) for level, title, _ in tgdocs.sections(text)] == headings


class BrokenDownload:
    """A response whose body breaks off: the connection is reset or times out mid-read."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        raise self.failure


# On Python 3.8 socket.timeout is not a TimeoutError; IncompleteRead and a reset are no URLError.
MID_DOWNLOAD_FAILURES = [socket.timeout("timed out"), http.client.IncompleteRead(b"part"), ConnectionResetError(104, "Connection reset by peer")]


@pytest.mark.parametrize("failure", MID_DOWNLOAD_FAILURES, ids=lambda failure: type(failure).__name__)
def test_a_download_that_breaks_off_is_reported_not_a_traceback(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", lambda request, timeout: BrokenDownload(failure))
    with pytest.raises(tgdocs.DocsError, match="cannot reach"):
        tgdocs.fetch("bots/api-changelog", fresh=False, allow_stale=False)


def answering(text: str):
    return lambda request, timeout: contextlib.nullcontext(io.BytesIO(text.encode("utf-8")))


def age_cache(directory) -> None:
    old = time.time() - tgdocs.CACHE_TTL_SECONDS - 60
    for path in directory.iterdir():
        os.utime(path, (old, old))


def test_a_download_that_breaks_off_falls_back_to_the_cache_only_when_allowed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("old page"))
    tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    age_cache(tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", lambda request, timeout: BrokenDownload(ConnectionResetError(104, "reset")))
    # Without the flag an old copy must never pass for the live docs.
    with pytest.raises(tgdocs.DocsError, match="A cached copy exists: rerun with --allow-stale"):
        tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    assert tgdocs.fetch("bots/faq", fresh=False, allow_stale=True) == "old page"
    assert "using a cached copy" in capsys.readouterr().err


def http_error(code: int):
    def answer(request, timeout):
        raise tgdocs.urllib.error.HTTPError(request.full_url, code, "Bad Gateway", {}, None)

    return answer


def test_a_server_error_falls_back_to_the_cache_only_when_allowed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("old page"))
    tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    age_cache(tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", http_error(502))
    with pytest.raises(tgdocs.DocsError, match="answered HTTP 502. A cached copy exists: rerun with --allow-stale"):
        tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    assert tgdocs.fetch("bots/faq", fresh=False, allow_stale=True) == "old page"
    assert "HTTP 502" in capsys.readouterr().err


def test_a_cache_that_cannot_be_written_costs_only_a_note(monkeypatch, tmp_path, capsys):
    blocker = tmp_path / "a file, not a folder"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(tgdocs, "CACHE_DIR", blocker / "telegram-bot-docs")
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("the page"))
    assert tgdocs.fetch("bots/faq", fresh=False, allow_stale=False) == "the page"
    assert capsys.readouterr().err.count("could not") == 1  # one note per failed change, none for what is not there
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", http_error(404))
    with pytest.raises(tgdocs.PageNotFound, match="does not exist"):
        tgdocs.fetch("bots/api/methods/nosuchmethod", fresh=False, allow_stale=False)
    assert "could not" in capsys.readouterr().err


@pytest.mark.parametrize("path", ["bots/no such", "bots/f\taq", "bots/\x7fpage"])
def test_a_path_with_spaces_or_control_characters_is_refused_before_any_request(monkeypatch, capsys, path):
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", lambda request, timeout: pytest.fail("no request expected"))
    assert run_main(monkeypatch, "page", path) == 1
    err = capsys.readouterr().err
    assert "is not a docs path" in err and "cannot reach" not in err


def test_a_cache_update_that_fails_leaves_the_old_copy_whole(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("old page"))
    tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    age_cache(tmp_path)

    def refused(source, target):
        # What Windows answers when another run has the cached file open.
        raise PermissionError(13, "The process cannot access the file because it is being used by another process")

    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("new page"))
    monkeypatch.setattr(tgdocs.os, "replace", refused)
    assert tgdocs.fetch("bots/faq", fresh=False, allow_stale=False) == "new page"
    assert [path.read_text(encoding="utf-8") for path in tmp_path.iterdir()] == ["old page"]
    assert "could not update the cache" in capsys.readouterr().err


def test_a_cache_update_leaves_only_the_new_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(tgdocs, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("old page"))
    tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    age_cache(tmp_path)
    monkeypatch.setattr(tgdocs.urllib.request, "urlopen", answering("new page"))
    tgdocs.fetch("bots/faq", fresh=False, allow_stale=False)
    assert [path.read_text(encoding="utf-8") for path in tmp_path.iterdir()] == ["new page"]
