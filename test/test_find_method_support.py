"""Tests for find_method_support.py against small fake libraries.

Run from the repository root (test/conftest.py makes the skill's scripts importable):
  uv run --with pytest --with hypothesis python -m pytest test
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

import find_method_support
from find_method_support import spellings

# Shaped like @grammyjs/types: a usage example in a doc comment, a parameter that belongs to
# another method, and a return type that looks like a parameter name.
TS_TYPES = """export interface ApiMethods<F> {
    /** Use this method to stream a partial message. You must call sendMessage to persist it. */
    sendMessageDraft(args: {
        chat_id: number;
        draft_id: number;
        can_stop?: boolean;
    }): true;
    /**
     * Use this method to send text messages.
     * Example: bot.api.sendMessage(chat_id, 'Hello', { can_stop: true })
     */
    sendMessage(args: {
        chat_id: number | string;
        text: string;
        ephemeral_message_parameters?: EphemeralMessageParameters;
    }): Message.TextMessage;
    /** Use this method to edit an ephemeral text or rich message. */
    editEphemeralMessageText(args: {
        chat_id: number | string;
        receiver_user_id: number;
    }): true;
    copyMessages(args: {
        chat_id: number | string;
        message_ids: number[];
    }): MessageId[];
    uploadStickerFile(args: {
        user_id: number;
        sticker_format: "static" | "animated" | "video";
    }): File;
}
"""

# Shaped like aiogram: one class per method, fields with docstrings that name other words.
PY_METHODS = '''from typing import Optional


class SendMessage(TelegramMethod[Message]):
    chat_id: int
    text: str
    ephemeral_message_parameters: Optional[EphemeralMessageParameters] = None


class EditEphemeralMessageText(TelegramMethod[bool]):
    chat_id: int
    receiver_user_id: int


class EditMessageCaption(TelegramMethod[Message]):
    caption: str | None = None
    """New caption of the message, 0-1024 characters after entities parsing"""
    caption_entities: list[MessageEntity] | None = None
    """A JSON-serialized list of special entities that appear in the caption"""
'''

# Shaped like python-telegram-bot: parameters in the signature; bodies, docstrings and return
# types around it must not count.
PY_SIGNATURE = '''class Bot:
    async def send_message(
        self,
        chat_id: int,
        text: str,
    ) -> Message:
        return await self._send_message(receiver_user_id=None)

    async def copy_messages(
        self,
        chat_id: int,
        message_ids: list[int],
    ) -> list[MessageId]:
        """Copies messages."""

    def send_dice(self, chat_id, emoji):
        """Mentions receiver_user_id in prose only."""
        return self._post(receiver_user_id=None)


def build(get_updates: bool = True, timeout: float = 5.0):
    return None
'''

# Shaped like go-telegram/bot: the method takes one parameters object defined elsewhere.
GO_PARAMS = """package bot

func (b *Bot) SendMessage(ctx context.Context, params *SendMessageParams) (*models.Message, error) {
\tresult := &models.Message{}
\terr := b.rawRequest(ctx, "sendMessage", params, &result)
\treturn result, err
}

type SendMessageParams struct {
\tChatID                     any                                `json:"chat_id"`
\tText                       string                             `json:"text"`
\tEphemeralMessageParameters *models.EphemeralMessageParameters `json:"ephemeral_message_parameters,omitempty"`
}
"""

# A minified bundle: every method on one line.
MINIFIED = (
    'class Api{sendMessage(e,t,n){return this.call("sendMessage",{chat_id:e,text:t})}'
    'editEphemeralMessageText(e,t,n){return this.call("editEphemeralMessageText",{receiver_user_id:t})}}\n'
)


def write(directory: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return directory


@pytest.fixture
def libs(tmp_path: Path) -> dict[str, Path]:
    (tmp_path / "project").mkdir()
    return {
        "ts": write(tmp_path / "ts-lib", {"methods.d.ts": TS_TYPES}),
        "py": write(tmp_path / "py-lib", {"methods.py": PY_METHODS}),
        "sig": write(tmp_path / "sig-lib", {"bot.py": PY_SIGNATURE}),
        "go": write(tmp_path / "go-lib", {"methods.go": GO_PARAMS}),
        "min": write(tmp_path / "min-lib", {"bundle.min.js": MINIFIED}),
        "two": write(
            tmp_path / "two-files",
            {
                "bot.d.ts": "/**\n * bot.api.sendMessage(chat_id, 'Hello, grammY!')\n */\nexport declare class Bot {}\n",
                "core/api.d.ts": 'export declare class Api {\n    sendMessage(chat_id: number | string, text: string, other?: Other<"sendMessage", "chat_id" | "text">): Promise<Message>;\n}\n',
            },
        ),
        "root": tmp_path / "project",
    }


def run(monkeypatch, capsys, lib: Path, root: Path, *names: str) -> str:
    monkeypatch.setattr(sys, "argv", ["find_method_support.py", *names, "--root", str(root), "--lib", str(lib)])
    assert find_method_support.main() == 0
    return capsys.readouterr().out


def status(out: str, query: str) -> str:
    match = re.search(rf"^\s+(found|MISSING)\s+{re.escape(query)}\b", out, re.M)
    assert match, f"no status line for {query} in:\n{out}"
    return match.group(1)


def test_a_parameter_inside_the_method_definition_is_found(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "sendMessage.ephemeral_message_parameters")
    assert status(out, "sendMessage.ephemeral_message_parameters") == "found"
    assert "methods.d.ts:15" in out


def test_a_parameter_of_another_method_is_not_credited_to_this_one(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "sendMessage.receiver_user_id")
    assert status(out, "sendMessage.receiver_user_id") == "MISSING"
    assert "methods.d.ts:20" in out  # where the name does occur, so the reader can look


def test_a_usage_example_in_a_doc_comment_is_not_a_definition(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "sendMessage.can_stop")
    assert status(out, "sendMessage.can_stop") == "MISSING"


def test_a_return_type_is_not_a_parameter(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "copyMessages.message_id", "copyMessages.message_ids")
    assert status(out, "copyMessages.message_id") == "MISSING"
    assert status(out, "copyMessages.message_ids") == "found"
    sig = run(monkeypatch, capsys, libs["sig"], libs["root"], "copy_messages.message_id")
    assert status(sig, "copy_messages.message_id") == "MISSING"


def test_a_quoted_value_is_not_a_parameter(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "uploadStickerFile.video", "uploadStickerFile.sticker_format")
    assert status(out, "uploadStickerFile.video") == "MISSING"
    assert status(out, "uploadStickerFile.sticker_format") == "found"


def test_any_spelling_of_method_and_parameter_matches_a_python_class(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["py"], libs["root"], "sendMessage.ephemeral_message_parameters", "send_message.receiverUserId")
    assert status(out, "sendMessage.ephemeral_message_parameters") == "found"
    assert status(out, "send_message.receiverUserId") == "MISSING"


def test_a_word_in_a_docstring_is_not_a_parameter(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["py"], libs["root"], "editMessageCaption.entities", "editMessageCaption.caption_entities")
    assert status(out, "editMessageCaption.entities") == "MISSING"
    assert status(out, "editMessageCaption.caption_entities") == "found"


def test_a_signature_ends_where_the_body_begins(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["sig"], libs["root"], "send_message.text", "send_message.receiver_user_id", "sendDice.emoji", "sendDice.receiver_user_id")
    assert status(out, "send_message.text") == "found"
    assert status(out, "send_message.receiver_user_id") == "MISSING"
    assert status(out, "sendDice.emoji") == "found"
    assert status(out, "sendDice.receiver_user_id") == "MISSING"


def test_a_type_annotation_is_not_a_definition(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["sig"], libs["root"], "getUpdates.timeout")
    assert status(out, "getUpdates.timeout") == "MISSING"


def test_a_parameters_object_of_the_method_counts(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["go"], libs["root"], "sendMessage.ephemeral_message_parameters", "sendMessage.receiver_user_id")
    assert status(out, "sendMessage.ephemeral_message_parameters") == "found"
    assert status(out, "sendMessage.receiver_user_id") == "MISSING"


def test_a_minified_bundle_credits_only_the_method_itself(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["min"], libs["root"], "sendMessage.receiver_user_id", "receiver_user_id")
    assert status(out, "sendMessage.receiver_user_id") == "MISSING"
    assert "receiver_user_id:t" in out  # the snippet shows the match, not the start of a long line


def test_the_definition_shown_is_a_declaration_not_a_doc_example(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["two"], libs["root"], "sendMessage.ephemeral_message_parameters")
    assert status(out, "sendMessage.ephemeral_message_parameters") == "MISSING"
    assert "core/api.d.ts:2" in out


def test_a_missing_method_is_reported_as_such(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "sendMessage", "sendNothing.text")
    assert status(out, "sendNothing.text") == "MISSING"
    assert "sendNothing not found" in out


def test_a_missing_pair_points_to_the_method_page_and_the_parameter_history(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "sendMessage.receiver_user_id")
    assert "tgdocs.py method sendMessage" in out
    assert "tgdocs.py history receiver_user_id" in out


def test_a_plain_name_shows_the_line_it_occurs_on(libs, monkeypatch, capsys):
    out = run(monkeypatch, capsys, libs["ts"], libs["root"], "receiver_user_id")
    assert status(out, "receiver_user_id") == "found"
    assert "receiver_user_id: number;" in out


# Words of two or more characters starting with a letter: the shape of Bot API names
# (sendMessage, MarkdownV2). Single-letter words are ambiguous by nature: "AB" in PascalCase
# cannot tell "a b" from "ab", so they are outside the domain.
name_words = st.lists(st.from_regex(r"[a-z][a-z0-9]{1,7}", fullmatch=True), min_size=1, max_size=5)


@given(name_words)
@example(["send", "message", "draft"])
@example(["markdown", "v2"])
@example(["ephemeral", "message", "parameters"])
@example(["me"])
def test_any_spelling_of_a_name_yields_all_its_spellings(words):
    camel = words[0] + "".join(w.capitalize() for w in words[1:])
    snake = "_".join(words)
    pascal = "".join(w.capitalize() for w in words)
    for written_as in (camel, snake, pascal):
        assert {camel, snake, pascal} <= spellings(written_as)


def test_a_large_minified_bundle_is_read_in_linear_time(tmp_path, monkeypatch, capsys):
    part = 'sendMessage(e,t,n){return this.call("sendMessage",{chat_id:e,x:"' + "a" * 300 + '"})}'
    lib = write(tmp_path / "big", {"bundle.min.js": "class Api{" + part * 2000 + "}\n"})
    (tmp_path / "project").mkdir()
    started = __import__("time").monotonic()
    out = run(monkeypatch, capsys, lib, tmp_path / "project", "sendMessage.receiver_user_id")
    assert status(out, "sendMessage.receiver_user_id") == "MISSING"
    assert __import__("time").monotonic() - started < 5  # was minutes: every match re-read its whole line


def test_output_prints_through_a_windows_code_page(libs, monkeypatch):
    lib = write(libs["root"].parent / "arrow-lib", {"api.ts": "// sends → receiver_user_id\nsendMessage(args: { receiver_user_id: number }): true;\n"})
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")  # a Windows pipe's default
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "argv", ["find_method_support.py", "receiver_user_id", "--root", str(libs["root"]), "--lib", str(lib)])
    assert find_method_support.main() == 0
    stream.flush()
    assert "sends → receiver_user_id" in stream.buffer.getvalue().decode("utf-8")
