#!/usr/bin/env python3

"""Produce bounded, safe projections of a Codex session transcript."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


VISIBLE_BLOCK_TYPES = {"input_text", "output_text", "text"}
HIDDEN_KEYS = {
    "encrypted_content",
    "reasoning",
    "reasoning_summary",
    "replacement_history",
    "internal_chat_message_metadata_passthrough",
}
SECRET_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "credentials",
    "oauth2_bearer",
    "pass",
    "password",
    "proxy_user",
    "set_cookie",
    "secret",
    "token",
    "userpwd",
    "access_key_id",
}
SECRET_KEY_PARTS = {
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "credentials",
    "pass",
    "passwd",
    "password",
    "secret",
    "token",
    "userpwd",
}
NON_SECRET_KEY_SUFFIXES = {
    "count",
    "enabled",
    "kind",
    "mode",
    "name",
    "status",
    "type",
}
WRAPPER_PREFIXES = (
    "<app-context",
    "<environment_context",
    "<permissions instructions",
    "<plugins_instructions",
    "<rehydrate-trigger",
    "<rehydrate-runtime",
    "<skills_instructions",
)
MAX_OUTPUT_BYTES = 16_000
MAX_SEARCH_TERMS = 8
MAX_TERM_CHARS = 256
MAX_SANITIZE_DEPTH = 64
QUERY_SCRIPT_NAMES = ("query_session.py", "query-session.py")
QUERY_COMMANDS = ("outline", "slice", "search", "show")
OUTPUT_CONTROL_CONTRACTS = {
    "outline": {"limit": (1, 24, 64), "preview-chars": (40, 120, 320)},
    "slice": {"limit": (1, 24, 32), "preview-chars": (40, 240, 500)},
    "search": {"limit": (1, 4, 12), "preview-chars": (40, 160, 400)},
    "show": {"limit": (1, 8, 12), "preview-chars": (80, 1_000, 2_000)},
}
HISTORY_PARSER_RE = re.compile(
    r"(?i)(?:\b(?:awk|bat|cat|findstr|gc|get-content|grep|head|jq|less|more|node|perl"
    r"|python(?:3(?:\.[0-9]+)?)?|rg|ruby|sed|sls|tail|type)\b"
    r"|convertfrom-json|decode_json|json\.loads|json\.parse"
    r"|json(?:document|node)\]\s*::\s*parse|jsonserializer\]\s*::\s*deserialize"
    r"|select-string)"
)
JS_COMMAND_FIELD_RE = re.compile(
    r"(?is)(?:[\"']?(?:cmd|command|script)[\"']?)\s*:\s*"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)"
)

ENCRYPTED_RE = re.compile(r"\bgAAAAA[A-Za-z0-9_-]{40,}\b")
PEM_RE = re.compile(
    r"-----BEGIN [^-\r\n]+-----.*?-----END [^-\r\n]+-----",
    re.DOTALL,
)
TOKEN_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)
TOKEN_MARKERS = (
    ("sk-", TOKEN_RES[0]),
    ("ghp_", TOKEN_RES[1]),
    ("gho_", TOKEN_RES[1]),
    ("ghs_", TOKEN_RES[1]),
    ("ghu_", TOKEN_RES[1]),
    ("github_pat_", TOKEN_RES[2]),
    ("AKIA", TOKEN_RES[3]),
)
GENERIC_KEY_PATTERN = r"[A-Za-z][A-Za-z0-9_.-]{0,127}"
SECRET_ASSIGN_RE = re.compile(
    rf"""
    (?<![A-Za-z0-9_])
    (?P<prefix>
        (?P<option>--|/|-)?["']?(?P<key>{GENERIC_KEY_PATTERN})["']?
        \s*(?::=|=>|:|=)\s*
    )
    (?:
        (?P<double>"(?:\\.|[^"\\])*")
        |(?P<single>'(?:\\.|[^'\\])*')
        |(?P<scheme>(?:basic|bearer|digest|negotiate)\s+[^\s,;]+)
        |(?P<unquoted>[^\s,;"']+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
USERINFO_ASSIGN_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    (?P<prefix>(?P<option>--|/|-)?["']?(?P<key>user)["']?\s*(?::=|=>|:|=)\s*)
    (?:
        (?P<double>"(?:\\.|[^"\\])*")
        |(?P<single>'(?:\\.|[^'\\])*')
        |(?P<scheme>(?:basic|bearer|digest|negotiate)\s+[^\s,;]+)
        |(?P<unquoted>[^\s,;"']+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
SPACE_SECRET_RE = re.compile(
    rf"""
    (?<!\S)
    (?P<prefix>
        (?P<key>
            (?:[A-Za-z0-9]+[._-])*
            (?:
                api[._-]?key|access[._-]?key(?:[._-]?id)?|auth(?:orization)?|bearer|
                credential(?:s)?|oauth2[._-]?bearer|pass(?:wd|word)?|private[._-]?key|
                secret|token|userpwd
            )
        )
        \s+(?:=>\s*)?
    )
    (?:
        (?P<double>"(?:\\.|[^"\\])*")
        |(?P<single>'(?:\\.|[^'\\])*')
        |(?P<scheme>(?:basic|bearer|digest|negotiate)\s+[^\s,;]+)
        |(?P<unquoted>[^\s,;]+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
CLI_SECRET_RE = re.compile(
    rf"""
    (?<!\S)
    (?P<prefix>(?:--|/|-)(?P<key>{GENERIC_KEY_PATTERN})\s+)
    (?:
        (?P<double>"(?:\\.|[^"\\])*")
        |(?P<single>'(?:\\.|[^'\\])*')
        |(?P<unquoted>[^\s,;]+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
URI_CREDENTIAL_RE = re.compile(
    r"(?i)(?P<scheme>(?:\b[a-z][a-z0-9+.-]*:)?//)[^/@\s]+@"
)
COOKIE_HEADER_RE = re.compile(
    r"(?i)\b(?P<prefix>(?:set-cookie|cookie)\s*:\s*)[^\r\n]+"
)
CLI_COMBINED_SECRET_KEYS = {"oauth2_bearer", "proxy_user", "user", "userpwd"}
CURL_CREDENTIAL_RE = re.compile(
    r"(?<!\S)(?P<prefix>-[uU]\s*)(?P<value>[^\s,;]*:[^\s,;]*)"
)
PASS_KEY_GATE_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_])(?:[A-Za-z0-9_.-]*[._-])?pass\s*(?:[:=]|\s)"
)
OPAQUE_CELL_HANDLE = r"([A-Za-z0-9][A-Za-z0-9._:-]{0,127})"
CELL_HANDLE_RES = (
    re.compile(rf"(?i)\bcell\s+id\s+{OPAQUE_CELL_HANDLE}\b"),
    re.compile(rf"(?i)[\"']?cell_id[\"']?\s*[:=]\s*[\"']?{OPAQUE_CELL_HANDLE}"),
)
SESSION_HANDLE_RE = re.compile(
    r"(?i)[\"']?session_id[\"']?\s*[:=]\s*[\"']?([0-9]+)(?![A-Za-z0-9_.:-])"
)
SECRET_TEXT_MARKERS = (
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "passwd",
    "password",
    "secret",
    "token",
    "access-key",
    "access_key",
    "accesskey",
    "private-key",
    "private_key",
    "privatekey",
    "userpwd",
)
EXIT_CODE_RE = re.compile(r"(?i)[\"']?exit_code[\"']?\s*[:=]\s*(-?[0-9]+)")
WHITESPACE_RE = re.compile(r"\s+")
RUNNING_STATUSES = {
    "in_progress",
    "incomplete",
    "paused",
    "pending",
    "processing",
    "queued",
    "requires_action",
    "running",
    "started",
}
FAILED_STATUSES = {
    "aborted",
    "canceled",
    "cancelled",
    "error",
    "failed",
    "failure",
    "rejected",
    "expired",
    "timed_out",
    "timeout",
}
SUCCEEDED_STATUSES = {"success", "succeeded"}


OMITTED = object()


@dataclass
class Record:
    line: int
    timestamp: str
    kind: str
    source: str
    text: str = ""
    role: str = ""
    name: str = ""
    call_id: str = ""
    record_id: str = ""
    turn_id: str = ""
    phase: str = ""
    status: str = ""
    window: int = 0
    aliases: list[int] = field(default_factory=list)
    handles: list[str] = field(default_factory=list)
    query_action: bool = False
    mirror_hash: str = ""
    input_incomplete: bool = False


@dataclass
class LoadedSession:
    records: list[Record]
    malformed_lines: list[int]
    skipped_invalid_utf8: list[int]

    @property
    def incomplete(self) -> bool:
        return bool(
            self.malformed_lines
            or self.skipped_invalid_utf8
            or any(record.input_incomplete for record in self.records)
        )


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def redact_text(text: str) -> str:
    if "gAAAAA" in text:
        text = ENCRYPTED_RE.sub("[REDACTED_ENCRYPTED]", text)
    if "-----BEGIN " in text:
        text = PEM_RE.sub("[REDACTED_PEM]", text)
    for marker, pattern in TOKEN_MARKERS:
        if marker in text:
            text = pattern.sub("[REDACTED_TOKEN]", text)
    if "//" in text and "@" in text:
        text = URI_CREDENTIAL_RE.sub(
            lambda match: f"{match.group('scheme')}[REDACTED]@",
            text,
        )
    if "cookie:" in text.casefold():
        text = COOKIE_HEADER_RE.sub(
            lambda match: f"{match.group('prefix')}[REDACTED]",
            text,
        )
    has_assignment = ":" in text or "=" in text
    has_cli_option = (
        "--" in text
        or " -" in text
        or " /" in text
        or text.startswith(("-", "/"))
    )
    lowered = text.casefold()
    has_curl_secret = "curl" in lowered and CURL_CREDENTIAL_RE.search(text) is not None
    has_pass_key = "pass" in lowered and PASS_KEY_GATE_RE.search(text) is not None
    has_userinfo_assignment = (
        "user" in lowered and has_assignment and ":" in text
    )
    has_combined_cli_secret = any(
        hint in lowered
        for hint in (
            "--oauth2-bearer ",
            "--oauth2-bearer=",
            "--proxy-user ",
            "--proxy-user=",
            "--user ",
            "--user=",
            "--userpwd ",
            "--userpwd=",
            " /user ",
        )
    ) or lowered.startswith("/user ")
    has_secret_marker = any(marker in lowered for marker in SECRET_TEXT_MARKERS)
    has_space_secret = (
        has_secret_marker or has_pass_key
    ) and SPACE_SECRET_RE.search(text) is not None
    if not (
        has_secret_marker
        or has_combined_cli_secret
        or has_curl_secret
        or has_pass_key
        or has_space_secret
        or has_userinfo_assignment
    ):
        return text

    def replacement(match: re.Match[str]) -> str:
        if match.group("double") is not None:
            value = '"[REDACTED]"'
        elif match.group("single") is not None:
            value = "'[REDACTED]'"
        else:
            value = "[REDACTED]"
        return f"{match.group('prefix')}{value}"

    def replace_assignment(match: re.Match[str]) -> str:
        option = match.groupdict().get("option")
        key = normalize_key(match.group("key"))
        raw_value = next(
            (
                match.group(name)
                for name in ("double", "single", "scheme", "unquoted")
                if match.groupdict().get(name) is not None
            ),
            "",
        )
        if not is_secret_key(key) and not (
            option and key in CLI_COMBINED_SECRET_KEYS
        ) and not (key == "user" and ":" in raw_value):
            return match.group(0)
        return replacement(match)

    def replace_cli(match: re.Match[str]) -> str:
        key = normalize_key(match.group("key"))
        if not is_secret_key(key) and key not in CLI_COMBINED_SECRET_KEYS:
            return match.group(0)
        return replacement(match)

    if has_assignment:
        text = SECRET_ASSIGN_RE.sub(replace_assignment, text)
    if has_userinfo_assignment:
        text = USERINFO_ASSIGN_RE.sub(replace_assignment, text)
    if has_cli_option:
        text = CLI_SECRET_RE.sub(replace_cli, text)
    if has_curl_secret:
        text = CURL_CREDENTIAL_RE.sub(
            lambda match: f"{match.group('prefix')}[REDACTED]",
            text,
        )
    if has_space_secret:
        text = SPACE_SECRET_RE.sub(replacement, text)
    return text


def compact_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def visible_blocks(value: Any) -> str | None:
    if not isinstance(value, list):
        return None

    saw_block = False
    texts: list[str] = []
    for item in value:
        if not isinstance(item, dict) or "type" not in item:
            continue
        saw_block = True
        raw_block_type = item.get("type")
        if not isinstance(raw_block_type, str):
            continue
        block_type = normalize_key(raw_block_type)
        if block_type not in VISIBLE_BLOCK_TYPES:
            continue
        text = item.get("text")
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts) if saw_block else None


def normalize_key(key: Any) -> str:
    raw = str(key)
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    return re.sub(r"[^a-z0-9]+", "_", snake.casefold()).strip("_")


def is_secret_key(key: Any) -> bool:
    normalized = normalize_key(key)
    parts = set(normalized.split("_"))
    if parts and normalized.split("_")[-1] in NON_SECRET_KEY_SUFFIXES:
        return False
    return (
        normalized in SECRET_KEYS
        or bool(parts.intersection(SECRET_KEY_PARTS))
        or normalized.endswith("_auth")
        or normalized.endswith(("api_key", "access_key", "access_key_id", "private_key"))
    )


def is_hidden_key(key: Any) -> bool:
    normalized = normalize_key(key)
    parts = set(normalized.split("_"))
    return normalized in HIDDEN_KEYS or bool(parts.intersection({"encrypted", "reasoning"}))


def sanitize_object(
    value: Any,
    *,
    depth: int = 0,
    incomplete: list[bool] | None = None,
) -> Any:
    if depth >= MAX_SANITIZE_DEPTH:
        if incomplete is not None:
            incomplete[0] = True
        return OMITTED
    if isinstance(value, dict):
        type_fields = [item for key, item in value.items() if normalize_key(key) == "type"]
        if type_fields:
            if len(type_fields) != 1:
                return OMITTED
            block_type = type_fields[0]
            content_field_present = any(
                normalize_key(key)
                in {"content", "data", "delta", "message", "payload", "summary", "text"}
                for key in value
            )
            if not isinstance(block_type, str):
                if content_field_present:
                    return OMITTED
            else:
                normalized_type = normalize_key(block_type)
                type_parts = set(normalized_type.split("_"))
                if normalized_type in VISIBLE_BLOCK_TYPES:
                    text_fields = [
                        item for key, item in value.items() if normalize_key(key) == "text"
                    ]
                    if len(text_fields) != 1 or not isinstance(text_fields[0], str):
                        return OMITTED
                    return {"type": normalized_type, "text": text_fields[0]}
                if type_parts.intersection({"encrypted", "reasoning"}) or content_field_present:
                    return OMITTED
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if is_hidden_key(key):
                continue
            if is_secret_key(key):
                clean[str(key)] = "[REDACTED]"
                continue
            clean_item = sanitize_object(
                item,
                depth=depth + 1,
                incomplete=incomplete,
            )
            if clean_item is not OMITTED:
                clean[str(key)] = clean_item
        return clean
    if isinstance(value, list):
        clean_items = [
            sanitize_object(item, depth=depth + 1, incomplete=incomplete) for item in value
        ]
        return [item for item in clean_items if item is not OMITTED]
    if isinstance(value, str):
        return value
    return value


def safe_tool_text(value: Any) -> tuple[str, bool]:
    incomplete = [False]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return value, False
            except RecursionError:
                return "[structured tool output omitted: nesting limit]", True
            sanitized = sanitize_object(parsed, incomplete=incomplete)
            if sanitized is OMITTED:
                return "[hidden tool-output block omitted]", incomplete[0]
            return (
                json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")),
                incomplete[0],
            )
        return value, False
    block_text = visible_blocks(value)
    if block_text is not None:
        return block_text, False
    sanitized = sanitize_object(value, incomplete=incomplete)
    if sanitized is OMITTED:
        return "[hidden tool-output block omitted]", incomplete[0]
    return (
        json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")),
        incomplete[0],
    )


def mirror_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def metadata_value(payload: dict[str, Any], key: str) -> str:
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    if isinstance(metadata, dict):
        value = metadata.get(key)
        if isinstance(value, str):
            return value
    return ""


def parse_timestamp(value: str) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def extract_handles(text: str) -> list[str]:
    handles: set[str] = set()
    for pattern in CELL_HANDLE_RES:
        handles.update(f"cell:{match}" for match in pattern.findall(text))
    handles.update(f"session:{match}" for match in SESSION_HANDLE_RE.findall(text))
    return sorted(handles)


def root_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalized_exit_code(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        return str(int(value))
    return None


def canonical_status(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = normalize_key(value)
    if normalized in RUNNING_STATUSES:
        return "running"
    if normalized in FAILED_STATUSES:
        return "failed"
    if normalized in SUCCEEDED_STATUSES:
        return "succeeded"
    if normalized == "completed":
        return "completed"
    return ""


def extract_call_status(text: str, payload_status: Any = None) -> str:
    status = canonical_status(payload_status)
    if status:
        return status
    lowered = text.casefold()
    if "script running with cell id" in lowered:
        return "running"
    if SESSION_HANDLE_RE.search(text) and "write_stdin" in lowered:
        return "running"
    return ""


def extract_status(text: str, payload_status: Any = None) -> str:
    status = canonical_status(payload_status)
    if status:
        return status

    root = root_json_object(text)
    if root is not None:
        exit_code = normalized_exit_code(root.get("exit_code"))
        if exit_code is not None:
            return f"exit:{exit_code}"
        if bool(root.get("error")) or root.get("is_error") is True or root.get("isError") is True:
            return "failed"
        status = canonical_status(root.get("status"))
        if status:
            return status
        if (
            normalized_exit_code(root.get("session_id")) is not None
            and "chunk_id" in root
            and "wall_time_seconds" in root
        ):
            return "running"
        return ""

    lowered = text.casefold()
    if "script running with cell id" in lowered:
        return "running"
    if SESSION_HANDLE_RE.search(text) and (
        "write_stdin" in lowered
        or ("chunk_id" in lowered and "wall_time_seconds" in lowered)
    ):
        return "running"
    script_completed = "script completed" in lowered
    if script_completed:
        exit_codes = EXIT_CODE_RE.findall(text)
        if exit_codes:
            return f"exit:{exit_codes[-1]}"
    if (
        "error:" in lowered
        or "traceback (most recent call last)" in lowered
        or "failed with http" in lowered
        or "command failed" in lowered
    ):
        return "failed"
    if script_completed:
        return "completed"
    return ""


def looks_like_wrapper(text: str) -> bool:
    return text.lstrip().casefold().startswith(WRAPPER_PREFIXES)


def command_strings(text: str) -> list[str]:
    root = root_json_object(text)
    commands: list[str] = []
    if root is not None:
        for key, value in root.items():
            if normalize_key(key) not in {"cmd", "command", "script"}:
                continue
            if isinstance(value, str):
                commands.append(value)
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                commands.append(" ".join(value))
    if "tools.exec_command" in text.casefold():
        for match in JS_COMMAND_FIELD_RE.finditer(text):
            literal = match.group("value")
            if literal.startswith("`"):
                commands.append(literal[1:-1])
                continue
            try:
                parsed = ast.literal_eval(literal)
            except (SyntaxError, ValueError):
                continue
            if isinstance(parsed, str):
                commands.append(parsed)
    return commands or [text]


def is_helper_invocation(command: str) -> bool:
    def basename(token: str) -> str:
        return token.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].casefold()

    tokenizations: list[list[str]] = []
    for posix in (True, False):
        try:
            tokens = shlex.split(command, posix=posix)
        except ValueError:
            continue
        if tokens and tokens not in tokenizations:
            tokenizations.append(tokens)

    wrappers = {
        "bash",
        "cmd",
        "cmd.exe",
        "command",
        "env",
        "powershell",
        "powershell.exe",
        "pwsh",
        "sh",
        "time",
        "uv",
        "zsh",
    }
    for tokens in tokenizations:
        first = 0
        while first < len(tokens) and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[first]
        ):
            first += 1
        if first >= len(tokens):
            continue
        script_indexes = [
            index
            for index, token in enumerate(tokens[:-1])
            if basename(token) in QUERY_SCRIPT_NAMES
            and tokens[index + 1].strip("\"'").casefold()
            in {"outline", "search", "show", "slice"}
        ]
        if not script_indexes:
            continue
        root = basename(tokens[first])
        if root in QUERY_SCRIPT_NAMES and script_indexes[0] == first:
            return True
        if re.fullmatch(r"(?:python(?:3(?:\.[0-9]+)?)?|py)(?:\.exe)?", root):
            return any(index > first for index in script_indexes)
        if root in wrappers:
            if any(
                any(
                    re.fullmatch(
                        r"(?:python(?:3(?:\.[0-9]+)?)?|py)(?:\.exe)?",
                        basename(token),
                    )
                    for token in tokens[first + 1 : index]
                )
                or index == first + 1
                for index in script_indexes
            ):
                return True
            for token in tokens[first + 1 :]:
                nested = token.strip("\"'")
                if nested != command and any(name in nested.casefold() for name in QUERY_SCRIPT_NAMES):
                    if is_helper_invocation(nested):
                        return True
    return False


def has_transcript_reference(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            ".codex/sessions/",
            ".codex\\sessions\\",
            "archived_sessions",
            "codex_thread_id",
            "transcript_path",
        )
    ) or ("rollout-" in lowered and ".jsonl" in lowered)


def is_transcript_reader(command: str) -> bool:
    if HISTORY_PARSER_RE.search(command) is None or not has_transcript_reference(command):
        return False

    def basename(token: str) -> str:
        return token.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].casefold()

    raw_readers = {"bat", "cat", "gc", "get-content", "head", "less", "more", "tail", "type"}
    search_readers = {
        "awk",
        "convertfrom-json",
        "findstr",
        "grep",
        "jq",
        "perl",
        "rg",
        "ruby",
        "sed",
        "select-string",
        "sls",
    }
    interpreters = {
        "node",
        "powershell",
        "powershell.exe",
        "pwsh",
    }
    wrappers = {"bash", "cmd", "cmd.exe", "sh", "zsh"}

    for posix in (True, False):
        try:
            tokens = shlex.split(command, posix=posix)
        except ValueError:
            continue
        first = 0
        while first < len(tokens) and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[first]
        ):
            first += 1
        if first >= len(tokens):
            continue
        root = basename(tokens[first])
        if re.fullmatch(r"(?:python(?:3(?:\.[0-9]+)?)?|py)(?:\.exe)?", root):
            return True
        if root in interpreters or root in wrappers:
            return True
        if root in raw_readers and any(
            has_transcript_reference(token) for token in tokens[first + 1 :]
        ):
            return True
        if (
            root in search_readers
            and len(tokens) > first + 1
            and not re.search(r"\s", tokens[-1])
            and has_transcript_reference(tokens[-1])
        ):
            return True
    return False


def looks_like_history_query(text: str) -> bool:
    if "*** begin patch" in text.casefold():
        return False
    for command in command_strings(text):
        lowered = command.casefold()
        if any(name in lowered for name in QUERY_SCRIPT_NAMES) and is_helper_invocation(command):
            return True
        if is_transcript_reader(command):
            return True
    return False


def make_record(
    line_number: int,
    timestamp: str,
    kind: str,
    source: str,
    text: str = "",
    payload: dict[str, Any] | None = None,
    window: int = 0,
    **values: Any,
) -> Record:
    payload = payload or {}
    clean_text = redact_text(text)
    record = Record(
        line=line_number,
        timestamp=timestamp,
        kind=kind,
        source=source,
        text=clean_text,
        record_id=str(payload.get("id", "")),
        turn_id=metadata_value(payload, "turn_id"),
        window=window,
        mirror_hash=mirror_hash(clean_text) if kind in {"user", "assistant"} else "",
        **values,
    )
    record.handles = extract_handles(clean_text)
    record.query_action = kind == "call" and looks_like_history_query(clean_text)
    return record


def parse_response_item(
    line_number: int,
    timestamp: str,
    payload: dict[str, Any],
    window: int,
) -> Record | None:
    payload_type = payload.get("type")
    if payload_type == "message":
        role = str(payload.get("role", ""))
        if role not in {"user", "assistant"}:
            return None
        raw_text = visible_blocks(payload.get("content"))
        if not raw_text or looks_like_wrapper(raw_text):
            return None
        return make_record(
            line_number,
            timestamp,
            role,
            "response_item.message",
            raw_text,
            payload,
            window,
            role=role,
            phase=str(payload.get("phase", "")),
        )
    if payload_type == "agent_message":
        raw_text = visible_blocks(payload.get("content"))
        if not raw_text:
            return None
        return make_record(
            line_number,
            timestamp,
            "assistant",
            "response_item.agent_message",
            raw_text,
            payload,
            window,
            role="assistant",
            name=str(payload.get("author", "")),
            phase="subagent",
        )
    if payload_type in {"function_call", "custom_tool_call"}:
        raw_value = payload.get("arguments") if payload_type == "function_call" else payload.get("input")
        text, input_incomplete = safe_tool_text(raw_value)
        status = extract_call_status(text, payload.get("status"))
        return make_record(
            line_number,
            timestamp,
            "call",
            f"response_item.{payload_type}",
            text,
            payload,
            window,
            name=str(payload.get("name", "")),
            call_id=str(payload.get("call_id", "")),
            status=status,
            input_incomplete=input_incomplete,
        )
    if payload_type in {"function_call_output", "custom_tool_call_output"}:
        text, input_incomplete = safe_tool_text(payload.get("output"))
        status = extract_status(text, payload.get("status"))
        return make_record(
            line_number,
            timestamp,
            "result",
            f"response_item.{payload_type}",
            text,
            payload,
            window,
            call_id=str(payload.get("call_id", "")),
            status=status,
            input_incomplete=input_incomplete,
        )
    return None


def response_item_closes_compaction_mirror(payload: dict[str, Any]) -> bool:
    payload_type = payload.get("type")
    normalized_type = normalize_key(payload_type) if isinstance(payload_type, str) else ""
    if set(normalized_type.split("_")).intersection({"encrypted", "reasoning"}):
        return False
    if normalized_type in {"agent_message", "message"}:
        raw_text = visible_blocks(payload.get("content"))
        if raw_text is None:
            return True
        return bool(raw_text and not looks_like_wrapper(raw_text))
    return True


def parse_event_message(
    line_number: int,
    timestamp: str,
    payload: dict[str, Any],
    window: int,
) -> Record | None:
    payload_type = payload.get("type")
    if payload_type not in {"user_message", "agent_message"}:
        return None
    raw_text = payload.get("message")
    if (
        not isinstance(raw_text, str)
        or not raw_text.strip()
        or looks_like_wrapper(raw_text)
    ):
        return None
    role = "user" if payload_type == "user_message" else "assistant"
    return make_record(
        line_number,
        timestamp,
        role,
        f"event_msg.{payload_type}",
        raw_text,
        payload,
        window,
        role=role,
        phase=str(payload.get("phase", "")),
    )


def merge_visible_messages(records: list[Record]) -> list[Record]:
    response_messages = [
        record for record in records if record.source == "response_item.message"
    ]
    event_messages = [record for record in records if record.source.startswith("event_msg.")]
    other_records = [
        record
        for record in records
        if record.source != "response_item.message" and not record.source.startswith("event_msg.")
    ]

    response_by_key: dict[tuple[int, str, str], list[Record]] = {}
    for record in response_messages:
        response_by_key.setdefault(
            (record.window, record.kind, record.mirror_hash), []
        ).append(record)
    event_by_key: dict[tuple[int, str, str], list[Record]] = {}
    for record in event_messages:
        event_by_key.setdefault(
            (record.window, record.kind, record.mirror_hash), []
        ).append(record)

    matched_response_lines: set[int] = set()
    merged: list[Record] = []

    def compatible(response: Record, event: Record) -> bool:
        response_time = parse_timestamp(response.timestamp)
        event_time = parse_timestamp(event.timestamp)
        time_distance = (
            abs(response_time - event_time)
            if response_time is not None and event_time is not None
            else float("inf")
        )
        return time_distance <= 2.0 or abs(response.line - event.line) <= 8

    def merge_pair(response: Record, event: Record) -> None:
        matched_response_lines.add(response.line)
        response.aliases = sorted({response.line, event.line})
        response.source = "response_item+event_msg"
        if not response.phase:
            response.phase = event.phase
        merged.append(response)

    for key, events in event_by_key.items():
        responses = response_by_key.get(key, [])
        response_index = 0
        available_responses: list[Record] = []
        unmatched_events: list[Record] = []
        for event in events:
            while (
                response_index < len(responses)
                and responses[response_index].line < event.line
            ):
                available_responses.append(responses[response_index])
                response_index += 1
            if available_responses and compatible(available_responses[-1], event):
                merge_pair(available_responses.pop(), event)
            else:
                unmatched_events.append(event)

        remaining_responses = available_responses + responses[response_index:]
        response_index = 0
        event_index = 0
        while response_index < len(remaining_responses) and event_index < len(unmatched_events):
            response = remaining_responses[response_index]
            event = unmatched_events[event_index]
            if response.line <= event.line:
                response_index += 1
            elif compatible(response, event):
                merge_pair(response, event)
                response_index += 1
                event_index += 1
            else:
                event.aliases = [event.line]
                merged.append(event)
                event_index += 1
        for event in unmatched_events[event_index:]:
            event.aliases = [event.line]
            merged.append(event)

    for response in response_messages:
        if response.line in matched_response_lines:
            continue
        if looks_like_wrapper(response.text):
            continue
        response.aliases = [response.line]
        response.source = "response_item.message-fallback"
        merged.append(response)

    return sorted(other_records + merged, key=lambda record: record.line)


def remove_synthesized_precompaction_assistant(
    records: list[Record], compaction_summaries: list[tuple[int, int, str]]
) -> list[Record]:
    removed_lines: set[int] = set()
    for boundary_line, prior_window, compacted_message in compaction_summaries:
        candidates = [
            record
            for record in records
            if record.kind == "assistant"
            and record.source != "response_item.agent_message"
            and record.window == prior_window
            and max({record.line, *record.aliases}) < boundary_line
            and record.line not in removed_lines
        ]
        if not candidates:
            continue
        nearest = max(candidates, key=lambda record: max({record.line, *record.aliases}))
        visible_text = nearest.text.strip()
        if visible_text and visible_text in compacted_message:
            removed_lines.add(nearest.line)
    return [record for record in records if record.line not in removed_lines]


def deduplicate_boundaries(records: list[Record]) -> list[Record]:
    return [record for record in records if record.status != "boundary-mirror"]


def load_session(path: Path) -> LoadedSession:
    records: list[Record] = []
    malformed_lines: list[int] = []
    skipped_invalid_utf8: list[int] = []
    window = 0
    last_compacted_line: int | None = None
    compaction_mirror_open = False
    compaction_summaries: list[tuple[int, int, str]] = []

    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            try:
                text_line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                skipped_invalid_utf8.append(line_number)
                continue
            if not text_line.strip():
                continue
            try:
                item = json.loads(text_line)
            except (json.JSONDecodeError, RecursionError):
                malformed_lines.append(line_number)
                continue
            if not isinstance(item, dict):
                malformed_lines.append(line_number)
                continue

            item_type = item.get("type")
            timestamp = str(item.get("timestamp", ""))
            payload = item.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            if item_type == "compacted":
                compacted_message = payload.get("message")
                if isinstance(compacted_message, str):
                    compaction_summaries.append(
                        (line_number, window, redact_text(compacted_message).strip())
                    )
                window += 1
                last_compacted_line = line_number
                compaction_mirror_open = True
                records.append(
                    make_record(
                        line_number,
                        timestamp,
                        "compaction",
                        "compacted",
                        payload=payload,
                        window=window,
                        status="boundary",
                    )
                )
                continue
            if item_type == "event_msg" and payload.get("type") == "context_compacted":
                mirrored = (
                    last_compacted_line is not None
                    and compaction_mirror_open
                    and line_number > last_compacted_line
                )
                if not mirrored:
                    window += 1
                records.append(
                    make_record(
                        line_number,
                        timestamp,
                        "compaction",
                        "event_msg.context_compacted",
                        payload=payload,
                        window=window,
                        status="boundary-mirror" if mirrored else "boundary-fallback",
                    )
                )
                last_compacted_line = None
                compaction_mirror_open = False
                continue
            if item_type == "response_item":
                record = parse_response_item(line_number, timestamp, payload, window)
                if record is not None:
                    records.append(record)
                if record is not None or response_item_closes_compaction_mirror(payload):
                    compaction_mirror_open = False
                continue
            if item_type == "event_msg":
                record = parse_event_message(line_number, timestamp, payload, window)
                if record is not None:
                    records.append(record)
                    compaction_mirror_open = False

    records = merge_visible_messages(records)
    records = remove_synthesized_precompaction_assistant(records, compaction_summaries)
    records = deduplicate_boundaries(records)
    return LoadedSession(records, malformed_lines, skipped_invalid_utf8)


def resolve_transcript(transcript: str | None, session_id: str | None) -> Path:
    if transcript:
        path = Path(transcript).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Transcript does not exist: {path}")
        return path

    resolved_session_id = session_id or os.environ.get("CODEX_THREAD_ID")
    if not resolved_session_id:
        raise ValueError("Provide --transcript or --session-id, or set CODEX_THREAD_ID")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    matches: list[Path] = []
    for directory_name in ("sessions", "archived_sessions"):
        directory = codex_home / directory_name
        if directory.is_dir():
            matches.extend(directory.rglob(f"*-{resolved_session_id}.jsonl"))
    unique_matches = sorted({path.resolve() for path in matches})
    if len(unique_matches) != 1:
        raise ValueError(
            f"Expected one transcript for session {resolved_session_id}, found {len(unique_matches)}"
        )
    return unique_matches[0]


def filter_records(
    records: Iterable[Record],
    args: argparse.Namespace,
    *,
    apply_lines: bool = True,
    apply_turn: bool = True,
) -> list[Record]:
    selected: list[Record] = []
    for record in records:
        if apply_lines and args.before_line is not None and record.line >= args.before_line:
            continue
        if apply_lines and args.after_line is not None and record.line <= args.after_line:
            continue
        if apply_turn and getattr(args, "turn_id", None) and record.turn_id != args.turn_id:
            continue
        if getattr(args, "window", None) is not None and record.window != args.window:
            continue
        selected.append(record)
    return selected


def build_action_components(records: list[Record]) -> tuple[list[list[Record]], set[int]]:
    actions = [record for record in records if record.kind in {"call", "result"}]
    if not actions:
        return [], set()
    union = UnionFind(len(actions))
    query_call_ids = {
        (record.window, record.call_id)
        for record in actions
        if record.kind == "call" and record.query_action and record.call_id
    }
    call_ids: dict[tuple[int, str], int] = {}
    for index, record in enumerate(actions):
        if record.call_id:
            call_key = (record.window, record.call_id)
            if call_key in call_ids:
                union.union(index, call_ids[call_key])
            else:
                call_ids[call_key] = index

    base_groups: dict[int, list[int]] = {}
    for index in range(len(actions)):
        base_groups.setdefault(union.find(index), []).append(index)

    handle_groups: dict[str, list[int]] = {}
    for root, indexes in base_groups.items():
        if any(
            (record.window, record.call_id) in query_call_ids
            for record in (actions[index] for index in indexes)
        ):
            continue
        component_handles = {
            handle for index in indexes for handle in actions[index].handles
        }
        for handle in component_handles:
            handle_groups.setdefault(handle, []).append(root)

    def explicit_continuation(indexes: list[int], handle: str) -> bool:
        for index in indexes:
            record = actions[index]
            if record.kind != "call" or handle not in record.handles:
                continue
            leaf_name = record.name.casefold().rsplit(".", 1)[-1]
            lowered_text = record.text.casefold()
            if leaf_name in {"wait", "write_stdin"} or "write_stdin" in lowered_text:
                return True
        return False

    for handle, roots in handle_groups.items():
        ordered_roots = sorted(
            set(roots),
            key=lambda root: min(actions[index].line for index in base_groups[root]),
        )
        if not ordered_roots:
            continue
        active_roots = [ordered_roots[0]]
        for root in ordered_roots[1:]:
            active_indexes = [index for active in active_roots for index in base_groups[active]]
            current_indexes = base_groups[root]
            active_records = sorted(
                (actions[index] for index in active_indexes),
                key=lambda record: record.line,
            )
            active_windows = {record.window for record in active_records}
            current_windows = {actions[index].window for index in current_indexes}
            active_state, _ = component_status(active_records)
            joins_active_chain = bool(active_windows.intersection(current_windows)) or (
                active_state in {"running", "unpaired"}
                and explicit_continuation(current_indexes, handle)
            )
            if joins_active_chain:
                union.union(base_groups[active_roots[0]][0], current_indexes[0])
                active_roots.append(root)
            else:
                active_roots = [root]

    grouped: dict[int, list[Record]] = {}
    for index, record in enumerate(actions):
        grouped.setdefault(union.find(index), []).append(record)
    components = [sorted(group, key=lambda record: record.line) for group in grouped.values()]
    components.sort(key=lambda group: group[-1].line)
    query_lines = {
        record.line
        for component in components
        if any(record.query_action for record in component)
        for record in component
    }
    return components, query_lines


def component_status(component: list[Record]) -> tuple[str, list[str]]:
    calls = {record.call_id for record in component if record.kind == "call" and record.call_id}
    results = {record.call_id for record in component if record.kind == "result" and record.call_id}
    unpaired = sorted(calls.symmetric_difference(results))
    latest_result_line = max(
        (record.line for record in component if record.kind == "result"),
        default=-1,
    )
    if any(
        record.kind == "call"
        and record.line > latest_result_line
        and (not record.call_id or record.call_id not in results)
        for record in component
    ):
        return "unpaired", unpaired
    for record in reversed(component):
        if record.kind != "result":
            continue
        if not record.call_id or record.call_id not in calls:
            return "unpaired", unpaired
        if record.status.startswith("exit:"):
            return ("succeeded" if record.status == "exit:0" else "failed"), unpaired
        if record.status == "succeeded":
            return "succeeded", unpaired
        if record.status == "failed":
            return "failed", unpaired
        if record.status == "running":
            return "running", unpaired
        return "completed-unverified", unpaired
    return "unpaired", unpaired


def excerpt(text: str, max_chars: int, terms: list[str] | None = None) -> tuple[str, bool]:
    compact = compact_whitespace(text)
    if len(compact) <= max_chars:
        return compact, False
    start = 0
    if terms:
        lowered = compact.casefold()
        positions = [lowered.find(term.casefold()) for term in terms]
        positions = [position for position in positions if position >= 0]
        if positions:
            start = max(0, min(positions) - max_chars // 3)
    end = min(len(compact), start + max_chars)
    value = compact[start:end]
    if start > 0:
        value = "..." + value[3:]
    if end < len(compact):
        value = value[:-3] + "..."
    return value, True


def query_diagnostic_text(record: Record) -> str:
    if record.status.startswith("exit:"):
        return f"[history-query exit_code={record.status.removeprefix('exit:')}]"
    if record.status:
        return f"[history-query status={record.status}]"
    return "[history-query body omitted]"


def record_projection(
    record: Record,
    preview_chars: int,
    terms: list[str] | None = None,
    include_excerpt: bool = True,
    diagnostic_only: bool = False,
) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "line": record.line,
        "timestamp": record.timestamp,
        "window": record.window,
        "kind": record.kind,
        "source": record.source,
    }
    optional = {
        "aliases": record.aliases if len(record.aliases) > 1 else [],
        "turn_id": record.turn_id,
        "phase": record.phase,
        "name": record.name,
        "call_id": record.call_id,
        "handles": [] if diagnostic_only else record.handles,
        "status": record.status,
        "record_id": record.record_id,
    }
    projected.update({key: value for key, value in optional.items() if value})
    if record.text and not diagnostic_only:
        projected["source_chars"] = len(record.text)
        if include_excerpt:
            preview, truncated = excerpt(record.text, preview_chars, terms)
            projected["excerpt"] = preview
            projected["excerpt_truncated"] = truncated
    elif diagnostic_only:
        preview, truncated = excerpt(query_diagnostic_text(record), preview_chars, terms)
        projected["excerpt"] = preview
        projected["excerpt_truncated"] = truncated
        projected["diagnostic_only"] = True
    return projected


def outline_projection(record: Record, preview_chars: int) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "line": record.line,
        "timestamp": record.timestamp,
        "window": record.window,
        "kind": record.kind,
    }
    if record.turn_id:
        projected["turn_id"] = record.turn_id
    if record.text:
        preview, truncated = excerpt(record.text, preview_chars)
        projected["source_chars"] = len(record.text)
        projected["excerpt"] = preview
        projected["excerpt_truncated"] = truncated
    return projected


def candidate_reference(record: Record, diagnostic_only: bool = False) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "line": record.line,
        "kind": record.kind,
    }
    optional = {
        "name": record.name,
        "call_id": record.call_id,
        "handles": [] if diagnostic_only else record.handles,
        "status": record.status,
    }
    projected.update({key: value for key, value in optional.items() if value})
    if record.text and not diagnostic_only:
        projected["source_chars"] = len(record.text)
    return projected


def candidate_evidence(
    record: Record,
    preview_chars: int,
    terms: list[str],
    diagnostic_only: bool = False,
) -> dict[str, Any]:
    projected = candidate_reference(record, diagnostic_only)
    selected_text = query_diagnostic_text(record) if diagnostic_only else record.text
    preview, truncated = excerpt(selected_text, preview_chars, terms)
    projected["excerpt"] = preview
    projected["excerpt_truncated"] = truncated
    if diagnostic_only:
        projected["diagnostic_only"] = True
    return projected


def base_metadata(command: str, loaded: LoadedSession) -> dict[str, Any]:
    sanitization_incomplete_lines = [
        record.line for record in loaded.records if record.input_incomplete
    ]
    return {
        "command": command,
        "safe_records": len(loaded.records),
        "input_incomplete": loaded.incomplete,
        "malformed_lines": loaded.malformed_lines[:10],
        "invalid_utf8_lines": loaded.skipped_invalid_utf8[:10],
        "sanitization_incomplete_lines": sanitization_incomplete_lines[:10],
    }


def paginate_records(
    records: list[Record], direction: str, limit: int
) -> tuple[list[Record], bool, dict[str, int]]:
    if direction == "backward":
        page = records[-limit:]
        has_more = len(records) > len(page)
        cursor = {"next_before_line": page[0].line} if has_more and page else {}
    else:
        page = records[:limit]
        has_more = len(records) > len(page)
        cursor = {"next_after_line": page[-1].line} if has_more and page else {}
    return page, has_more, cursor


def item_cursor_line(item: dict[str, Any], mode: str) -> int | None:
    keys = (
        ("anchor_line", "line", "start_line")
        if mode == "before"
        else ("line", "anchor_line", "start_line")
    )
    for key in keys:
        value = item.get(key)
        if isinstance(value, int):
            return value
    return None


def cursor_mode(payload: dict[str, Any]) -> str | None:
    if payload.get("command") == "search":
        return "before"
    if payload.get("command") == "show":
        return "after"
    direction = payload.get("direction")
    if direction == "backward":
        return "before"
    if direction == "forward":
        return "after"
    return None


def refresh_cursor(payload: dict[str, Any], items: list[dict[str, Any]]) -> None:
    mode = cursor_mode(payload)
    if not payload.get("has_more") or not items or mode is None:
        return
    lines = [
        line
        for item in items
        if (line := item_cursor_line(item, mode)) is not None
    ]
    if not lines:
        return
    if mode == "before":
        cursor_key = (
            "next_cursor_before_line"
            if payload.get("command") == "search"
            else "next_before_line"
        )
        payload[cursor_key] = min(lines)
    else:
        payload["next_after_line"] = max(lines)


def bounded_item_stub(item: dict[str, Any]) -> dict[str, Any]:
    stub: dict[str, Any] = {}
    for key in (
        "line",
        "start_line",
        "anchor_line",
        "window",
        "kind",
        "state",
        "status",
        "record_count",
        "source_chars",
    ):
        value = item.get(key)
        if isinstance(value, (int, bool)):
            stub[key] = value
        elif isinstance(value, str):
            stub[key] = value[:256]
    matched_terms = item.get("matched_terms")
    if isinstance(matched_terms, list):
        stub["matched_term_count"] = len(matched_terms)
    stub["projection_limited"] = True
    if item.get("kind") == "action-chain":
        stub["references_incomplete"] = True
    return stub


def render_json(payload: dict[str, Any]) -> bytes:
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return rendered.encode("utf-8", errors="backslashreplace")


def write_json(encoded: bytes) -> None:
    binary = getattr(sys.stdout, "buffer", None)
    if binary is not None:
        binary.write(encoded + b"\n")
        binary.flush()
    else:
        sys.stdout.write(encoded.decode("utf-8") + "\n")
        sys.stdout.flush()


def emit_bounded(payload: dict[str, Any], item_key: str, preserve_newest: bool) -> None:
    items = payload.get(item_key)
    if not isinstance(items, list):
        write_json(render_json(payload))
        return
    refresh_cursor(payload, items)
    projection_reduced = False
    while True:
        rendered = render_json(payload)
        if len(rendered) + 1 <= MAX_OUTPUT_BYTES:
            write_json(rendered)
            return
        payload["output_limited"] = True
        payload["needs_refinement"] = True
        if len(items) > 1:
            if preserve_newest:
                items.pop(0)
            else:
                items.pop()
            payload["returned"] = len(items)
            payload["has_more"] = True
            refresh_cursor(payload, items)
            continue
        if items and not projection_reduced:
            items[0] = bounded_item_stub(items[0])
            payload["projection_limited"] = True
            projection_reduced = True
            continue
        fallback = {
            "command": payload.get("command", "unknown"),
            "input_incomplete": True,
            "output_limited": True,
            "needs_refinement": True,
            "error": "Bounded metadata could not be projected safely",
        }
        write_json(render_json(fallback))
        return


def command_outline(args: argparse.Namespace, loaded: LoadedSession) -> None:
    records = filter_records(loaded.records, args)
    records = [record for record in records if record.kind in {"user", "compaction"}]
    page, has_more, cursor = paginate_records(records, args.direction, args.limit)
    payload = base_metadata("outline", loaded)
    payload.update(
        {
            "direction": args.direction,
            "total_candidates": len(records),
            "returned": len(page),
            "has_more": has_more,
            "needs_refinement": loaded.incomplete or has_more,
            **cursor,
            "items": [outline_projection(record, args.preview_chars) for record in page],
        }
    )
    emit_bounded(payload, "items", preserve_newest=args.direction == "backward")


def command_slice(args: argparse.Namespace, loaded: LoadedSession) -> None:
    records = filter_records(loaded.records, args)
    graph_records = filter_records(
        loaded.records,
        args,
        apply_lines=False,
        apply_turn=False,
    )
    components, query_lines = build_action_components(graph_records)
    del components
    if not args.include_query_actions:
        records = [record for record in records if record.line not in query_lines]
    if args.kind:
        kinds = set(args.kind)
        records = [record for record in records if record.kind in kinds]
    records = [record for record in records if record.kind != "compaction"]
    page, has_more, cursor = paginate_records(records, args.direction, args.limit)
    payload = base_metadata("slice", loaded)
    payload.update(
        {
            "direction": args.direction,
            "total_candidates": len(records),
            "returned": len(page),
            "has_more": has_more,
            "needs_refinement": loaded.incomplete or has_more,
            **cursor,
            "items": [
                record_projection(
                    record,
                    args.preview_chars,
                    diagnostic_only=record.line in query_lines,
                )
                for record in page
            ],
        }
    )
    emit_bounded(payload, "items", preserve_newest=args.direction == "backward")


def action_candidate(
    component: list[Record],
    terms: list[str],
    preview_chars: int,
    diagnostic_only: bool = False,
) -> dict[str, Any]:
    status, unpaired = component_status(component)
    query_component = diagnostic_only or any(record.query_action for record in component)
    search_texts = [
        query_diagnostic_text(record) if query_component else record.text
        for record in component
    ]
    combined = "\n".join(search_texts)
    matched_terms = [term for term in terms if term.casefold() in combined.casefold()]
    matching_records = [
        record
        for record, search_text in zip(component, search_texts)
        if any(term.casefold() in search_text.casefold() for term in matched_terms)
    ]
    if not matching_records:
        matching_records = component[-1:]
    evidence = [
        candidate_evidence(
            record,
            preview_chars,
            matched_terms,
            diagnostic_only=query_component,
        )
        for record in matching_records[:2]
    ]
    references = [
        candidate_reference(record, diagnostic_only=query_component)
        for record in component[:10]
    ]
    return {
        "start_line": component[0].line,
        "anchor_line": component[-1].line,
        "kind": "action-chain",
        "windows": sorted({record.window for record in component}),
        "turn_ids": sorted({record.turn_id for record in component if record.turn_id}),
        "call_ids": sorted({record.call_id for record in component if record.call_id}),
        "handles": (
            []
            if query_component
            else sorted({handle for record in component for handle in record.handles})
        ),
        "state": status,
        "unpaired_call_ids": unpaired,
        "matched_terms": [redact_text(term) for term in matched_terms],
        "record_count": len(component),
        "references_incomplete": len(component) > len(references),
        "records": references,
        "evidence": evidence,
    }


def message_candidate(record: Record, terms: list[str], preview_chars: int) -> dict[str, Any]:
    matched_terms = [term for term in terms if term.casefold() in record.text.casefold()]
    return {
        "start_line": record.line,
        "anchor_line": record.line,
        "kind": record.kind,
        "turn_id": record.turn_id,
        "matched_terms": [redact_text(term) for term in matched_terms],
        "record": candidate_evidence(record, preview_chars, matched_terms),
    }


def command_search(args: argparse.Namespace, loaded: LoadedSession) -> None:
    records = filter_records(loaded.records, args)
    if args.cursor_before_line is not None:
        records = [record for record in records if record.line < args.cursor_before_line]
    component_records = filter_records(
        loaded.records,
        args,
        apply_turn=False,
    )
    components, _ = build_action_components(component_records)
    _, query_lines = build_action_components(loaded.records)
    components = [
        component
        for component in components
        if (args.cursor_before_line is None or component[-1].line < args.cursor_before_line)
        and (
            not args.turn_id
            or any(record.turn_id == args.turn_id for record in component)
        )
    ]
    if not args.include_query_actions:
        components = [
            component
            for component in components
            if not any(record.line in query_lines for record in component)
        ]

    terms = args.term

    def matches(text: str) -> bool:
        checks = [term.casefold() in text.casefold() for term in terms]
        return all(checks) if args.match == "all" else any(checks)

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for component in components:
        query_component = any(record.line in query_lines for record in component)
        combined = "\n".join(
            query_diagnostic_text(record) if query_component else record.text
            for record in component
        )
        if matches(combined):
            candidates.append(
                (
                    component[-1].line,
                    component[0].line,
                    action_candidate(
                        component,
                        terms,
                        args.preview_chars,
                        diagnostic_only=query_component,
                    ),
                )
            )
    if args.include_messages:
        for record in records:
            if record.kind not in {"user", "assistant"} or not record.text:
                continue
            if matches(record.text):
                candidates.append(
                    (
                        record.line,
                        record.line,
                        message_candidate(record, terms, args.preview_chars),
                    )
                )

    candidates.sort(key=lambda item: item[0], reverse=True)
    total_matches = len(candidates)
    page = candidates[: args.limit]
    has_more = total_matches > len(page)
    payload = base_metadata("search", loaded)
    payload.update(
        {
            "match": args.match,
            "terms": [redact_text(term) for term in terms],
            "total_matches": total_matches,
            "returned": len(page),
            "has_more": has_more,
            "needs_refinement": loaded.incomplete or has_more,
            "next_cursor_before_line": (
                min(item[0] for item in page) if has_more and page else None
            ),
            "matches": [item[2] for item in page],
        }
    )
    if payload["next_cursor_before_line"] is None:
        payload.pop("next_cursor_before_line")
    emit_bounded(payload, "matches", preserve_newest=False)


def command_show(args: argparse.Namespace, loaded: LoadedSession) -> None:
    scope_records = filter_records(
        loaded.records,
        args,
        apply_lines=False,
        apply_turn=False,
    )
    if args.before_line is not None:
        scope_records = [
            record for record in scope_records if record.line < args.before_line
        ]
    selector_records = [
        record
        for record in scope_records
        if not args.turn_id or record.turn_id == args.turn_id
    ]
    components, query_lines = build_action_components(scope_records)
    line_map = {
        alias: record
        for record in selector_records
        for alias in ({record.line, *record.aliases})
        if args.before_line is None or alias < args.before_line
    }
    selected: dict[int, Record] = {}
    for line in args.line:
        record = line_map.get(line)
        if record is not None:
            selected[record.line] = record
    for record in selector_records:
        if record.call_id and record.call_id in args.call_id:
            selected[record.line] = record
        if record.line not in query_lines and set(record.handles).intersection(args.handle):
            selected[record.line] = record
    if args.turn_id:
        for record in selector_records:
            if record.turn_id == args.turn_id and record.line not in query_lines:
                selected[record.line] = record

    if args.include_related and selected:
        selected_lines = set(selected)
        selected_call_ids = {record.call_id for record in selected.values() if record.call_id}
        selected_handles = {
            handle
            for record in selected.values()
            if record.line not in query_lines
            for handle in record.handles
        }
        for component in components:
            directly_selected = (
                any(record.line in selected_lines for record in component)
                or any(record.call_id in selected_call_ids for record in component if record.call_id)
            )
            query_component = any(record.line in query_lines for record in component)
            shares_handle = any(
                set(record.handles).intersection(selected_handles) for record in component
            )
            if directly_selected or (shares_handle and not query_component):
                for record in component:
                    selected[record.line] = record

    ordered = sorted(
        (
            record
            for record in selected.values()
            if args.after_line is None or record.line > args.after_line
        ),
        key=lambda record: record.line,
    )
    total_selected = len(ordered)
    page = ordered[: args.limit]
    has_more = total_selected > len(page)
    payload = base_metadata("show", loaded)
    payload.update(
        {
            "selected": total_selected,
            "returned": len(page),
            "has_more": has_more,
            "needs_refinement": loaded.incomplete or has_more,
            "items": [
                record_projection(
                    record,
                    args.preview_chars,
                    args.term,
                    diagnostic_only=record.line in query_lines,
                )
                for record in page
            ],
        }
    )
    if has_more and page:
        payload["next_after_line"] = page[-1].line
    emit_bounded(payload, "items", preserve_newest=False)


def capped_int(minimum: int, maximum: int):
    def parse(value: str) -> int:
        number = int(value)
        if number < minimum:
            raise argparse.ArgumentTypeError(
                f"expected at least {minimum}; values above {maximum} are capped"
            )
        return min(number, maximum)

    return parse


def add_output_control(
    parser: argparse.ArgumentParser,
    command: str,
    option: str,
    description: str,
) -> None:
    minimum, default, maximum = OUTPUT_CONTROL_CONTRACTS[command][option]
    parser.add_argument(
        f"--{option}",
        type=capped_int(minimum, maximum),
        default=default,
        metavar=f"{minimum}..{maximum}",
        help=(
            f"{description} (default: {default}; minimum: {minimum}; cap: {maximum}; "
            "values above the cap are capped)"
        ),
    )


def output_control_help() -> str:
    rows = []
    for command in QUERY_COMMANDS:
        limit_minimum, limit_default, limit_maximum = OUTPUT_CONTROL_CONTRACTS[command]["limit"]
        preview_minimum, preview_default, preview_maximum = OUTPUT_CONTROL_CONTRACTS[command][
            "preview-chars"
        ]
        rows.append(
            f"  {command}: --limit {limit_default} ({limit_minimum}..{limit_maximum}); "
            f"--preview-chars {preview_default} ({preview_minimum}..{preview_maximum})"
        )
    return "\n".join(rows)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transcript")
    parser.add_argument("--session-id")
    parser.add_argument("--before-line", type=int)
    parser.add_argument("--after-line", type=int)
    parser.add_argument("--turn-id")
    parser.add_argument("--window", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Use one launcher: query_session.py <outline|slice|search|show> [options].\n"
            "The four names are positional subcommands, not separate *_session.py files.\n"
            "Output controls show default (minimum..cap); values above a cap are capped:\n"
            f"{output_control_help()}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    outline = subparsers.add_parser("outline", help="List genuine user messages and compaction boundaries")
    add_common_arguments(outline)
    outline.add_argument("--direction", choices=("backward", "forward"), default="backward")
    add_output_control(outline, "outline", "limit", "Maximum records per page")
    add_output_control(outline, "outline", "preview-chars", "Maximum characters per excerpt")
    outline.set_defaults(handler=command_outline)

    slice_parser = subparsers.add_parser("slice", help="Page through safe records in a selected span or turn")
    add_common_arguments(slice_parser)
    slice_parser.add_argument("--direction", choices=("backward", "forward"), default="backward")
    add_output_control(slice_parser, "slice", "limit", "Maximum records per page")
    add_output_control(slice_parser, "slice", "preview-chars", "Maximum characters per excerpt")
    slice_parser.add_argument(
        "--kind",
        action="append",
        choices=("user", "assistant", "call", "result"),
    )
    slice_parser.add_argument("--include-query-actions", action="store_true")
    slice_parser.set_defaults(handler=command_slice)

    search = subparsers.add_parser("search", help="Find bounded candidates using literal term intersections")
    add_common_arguments(search)
    search.add_argument("--term", action="append", required=True)
    search.add_argument("--cursor-before-line", type=int)
    search.add_argument("--match", choices=("all", "any"), default="all")
    add_output_control(search, "search", "limit", "Maximum candidates per page")
    add_output_control(search, "search", "preview-chars", "Maximum characters per excerpt")
    search.add_argument("--include-query-actions", action="store_true")
    search.add_argument("--include-messages", action="store_true")
    search.set_defaults(handler=command_search)

    show = subparsers.add_parser("show", help="Expand selected safe records and related action chains")
    add_common_arguments(show)
    show.add_argument("--line", action="append", type=int, default=[])
    show.add_argument("--call-id", action="append", default=[])
    show.add_argument("--handle", action="append", default=[])
    show.add_argument("--term", action="append", default=[])
    show.add_argument("--include-related", action="store_true")
    add_output_control(show, "show", "limit", "Maximum selected records per page")
    add_output_control(show, "show", "preview-chars", "Maximum characters per excerpt")
    show.set_defaults(handler=command_show)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        transcript = resolve_transcript(args.transcript, args.session_id)
        loaded = load_session(transcript)
        if args.command == "show" and not (
            args.line or args.call_id or args.handle or args.turn_id
        ):
            raise ValueError("show requires --line, --call-id, --handle, or --turn-id")
        if args.command == "search":
            if len(args.term) > MAX_SEARCH_TERMS:
                raise ValueError(f"search accepts at most {MAX_SEARCH_TERMS} terms")
            if any(not term.strip() for term in args.term):
                raise ValueError("search terms must not be empty")
            if any(len(term) > MAX_TERM_CHARS for term in args.term):
                raise ValueError(f"search terms must be at most {MAX_TERM_CHARS} characters")
        args.handler(args, loaded)
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error), "incomplete": True}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
