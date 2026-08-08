#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "plugins" / "rehydrate" / "scripts" / "query_session.py"


def message(role, text, turn_id, phase=None):
    payload = {
        "type": "message",
        "id": f"message-{turn_id}-{role}-{len(text)}",
        "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
        "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
    }
    if phase:
        payload["phase"] = phase
    return {"type": "response_item", "payload": payload}


def event(role, text):
    event_type = "user_message" if role == "user" else "agent_message"
    payload = {"type": event_type, "message": text}
    if role == "assistant":
        payload["phase"] = "commentary"
    return {"type": "event_msg", "payload": payload}


def call(call_id, name, value, turn_id, custom=True):
    payload = {
        "type": "custom_tool_call" if custom else "function_call",
        "id": f"call-{call_id}",
        "call_id": call_id,
        "name": name,
        "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
    }
    payload["input" if custom else "arguments"] = value
    return {"type": "response_item", "payload": payload}


def result(call_id, value, turn_id, custom=True, status=None):
    payload = {
        "type": "custom_tool_call_output" if custom else "function_call_output",
        "id": f"result-{call_id}",
        "call_id": call_id,
        "output": value,
        "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
    }
    if status is not None:
        payload["status"] = status
    return {"type": "response_item", "payload": payload}


class QuerySessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.transcript = Path(self.temp_dir.name) / "rollout-test-session.jsonl"
        records = []

        def add(item):
            item["timestamp"] = f"2026-08-04T00:00:{len(records):02d}.000Z"
            records.append(item)

        add(message("user", "Initial target: keep alpha", "turn-initial"))
        add(event("user", "Initial target: keep alpha"))
        add(message("assistant", "I will inspect alpha.", "turn-initial", "commentary"))
        add(event("assistant", "I will inspect alpha."))
        add(
            {
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"text": "FORBIDDEN_REASONING HTTP 403"}],
                },
            }
        )
        add(
            {
                "type": "compacted",
                "payload": {
                    "message": "FORBIDDEN_COMPACT_SUMMARY",
                    "replacement_history": [{"role": "user", "content": "FORBIDDEN_REPLACEMENT"}],
                },
            }
        )
        add({"type": "event_msg", "payload": {"type": "context_compacted"}})
        add(message("user", "<environment_context>FORBIDDEN_WRAPPER</environment_context>", "turn-change"))
        add(message("user", "Correction: use beta instead", "turn-change"))
        add(event("user", "Correction: use beta instead"))
        add(message("assistant", "Checking the manual fetch.", "turn-change", "commentary"))
        add(event("assistant", "Checking the manual fetch."))
        add(call("call-start", "exec", "run manual-fetch through proxy", "turn-change"))
        add(result("call-start", "Script running with cell ID 92", "turn-change"))
        add(call("call-wait", "wait", '{"cell_id":"92"}', "turn-change", custom=False))
        add(
            result(
                "call-wait",
                [{"type": "input_text", "text": '{"session_id":3407,"output":""}'}],
                "turn-change",
                custom=False,
            )
        )
        add(call("call-finish", "exec", "write_stdin session_id: 3407", "turn-change"))
        huge_output = (
            "Script completed\n"
            + ("irrelevant filler " * 70000)
            + '\n{"exit_code":1,"output":"manual-fetch failed with HTTP 403"}'
        )
        add(result("call-finish", huge_output, "turn-change"))
        add(
            call(
                "call-query",
                "exec",
                "python3 /plugin/scripts/query_session.py search --term manual-fetch "
                "--term 'HTTP 403' --transcript rollout-test-session.jsonl",
                "turn-change",
            )
        )
        add(
            result(
                "call-query",
                json.dumps(
                    {
                        "command": "search",
                        "input_incomplete": False,
                        "error": "history echo: manual-fetch HTTP 403",
                        "matches": [
                            {
                                "excerpt": "private query echo cell_id:92 session_id:3407"
                            }
                        ],
                    }
                ),
                "turn-change",
            )
        )
        add(call("call-unpaired", "exec", "manual-fetch pending", "turn-change"))
        add(
            result(
                "call-secret",
                "Authorization: Bearer super-secret-token sk-abcdefghijklmnopqrstuvwxyz",
                "turn-change",
            )
        )
        add(
            {
                "type": "response_item",
                "payload": {
                    "type": "agent_message",
                    "id": "agent-secret",
                    "author": "/root/subagent",
                    "content": [
                        {"type": "input_text", "text": "Visible subagent note"},
                        {"type": "encrypted_content", "encrypted_content": "gAAAAASECRET_PAYLOAD"},
                    ],
                    "internal_chat_message_metadata_passthrough": {"turn_id": "turn-change"},
                },
            }
        )
        add(message("user", "Initial target: keep alpha", "turn-repeat"))
        add(event("user", "Initial target: keep alpha"))
        add(message("user", "Unicode check: \u4e2d\u6587", "turn-unicode"))
        add(event("user", "Unicode check: \u4e2d\u6587"))

        with self.transcript.open("w", encoding="utf-8") as handle:
            for item in records:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            handle.write("{malformed final line\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_transcript(self, name, records):
        transcript = Path(self.temp_dir.name) / name
        with transcript.open("w", encoding="utf-8") as handle:
            for index, item in enumerate(records):
                item["timestamp"] = (
                    f"2026-08-04T{(3 + index // 3600) % 24:02d}:"
                    f"{(index // 60) % 60:02d}:{index % 60:02d}.000Z"
                )
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        return transcript

    def run_query_on(self, transcript, *args, env=None):
        result = subprocess.run(
            [sys.executable, str(QUERY), *args, "--transcript", str(transcript)],
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 16000)
        return json.loads(result.stdout), result.stdout

    def run_query(self, *args):
        return self.run_query_on(self.transcript, *args)

    def test_help_exposes_single_launcher_and_output_control_contracts(self):
        root_help = subprocess.run(
            [sys.executable, str(QUERY), "--help"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn(
            "query_session.py <outline|slice|search|show>",
            root_help,
        )
        self.assertIn("not separate *_session.py files", root_help)

        contracts = {
            "outline": ((1, 24, 64), (40, 120, 320)),
            "slice": ((1, 24, 32), (40, 240, 500)),
            "search": ((1, 4, 12), (40, 160, 400)),
            "show": ((1, 8, 12), (80, 1_000, 2_000)),
        }
        for command, (limit, preview) in contracts.items():
            with self.subTest(command=command):
                command_help = subprocess.run(
                    [sys.executable, str(QUERY), command, "--help"],
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout
                compact_help = " ".join(command_help.split())
                for minimum, default, maximum in (limit, preview):
                    self.assertIn(f"default: {default}", compact_help)
                    self.assertIn(f"minimum: {minimum}", compact_help)
                    self.assertIn(f"cap: {maximum}", compact_help)
                self.assertIn("values above the cap are capped", compact_help)

    def test_output_controls_cap_high_values_but_reject_low_or_non_integer_values(self):
        def excerpts(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "excerpt" and isinstance(item, str):
                        yield item
                    else:
                        yield from excerpts(item)
            elif isinstance(value, list):
                for item in value:
                    yield from excerpts(item)

        capped_search_transcript = self.write_transcript(
            "capped-search.jsonl",
            [
                item
                for index in range(13)
                for item in (
                    call(
                        f"cap-{index}",
                        "exec",
                        "cap-target " + ("x" * 600),
                        "turn-cap",
                    ),
                    result(
                        f"cap-{index}",
                        '{"exit_code":0,"output":"done"}',
                        "turn-cap",
                    ),
                )
            ],
        )
        search, _ = self.run_query_on(
            capped_search_transcript,
            "search",
            "--term",
            "cap-target",
            "--limit",
            "16",
            "--preview-chars",
            "500",
        )
        search_excerpts = list(excerpts(search))
        self.assertEqual(search["returned"], 12)
        self.assertTrue(search["has_more"])
        self.assertTrue(search_excerpts)
        self.assertLessEqual(max(map(len, search_excerpts)), 400)

        capped_show_transcript = self.write_transcript(
            "capped-show.jsonl",
            [message("user", "y" * 2_100, "turn-preview-cap")],
        )
        shown, _ = self.run_query_on(
            capped_show_transcript,
            "show",
            "--line",
            "1",
            "--limit",
            "99",
            "--preview-chars",
            "2500",
        )
        shown_excerpts = list(excerpts(shown))
        self.assertLessEqual(shown["returned"], 12)
        self.assertTrue(shown_excerpts)
        self.assertLessEqual(max(map(len, shown_excerpts)), 2_000)
        self.assertIn(2_000, map(len, shown_excerpts))

        too_low = subprocess.run(
            [
                sys.executable,
                str(QUERY),
                "show",
                "--line",
                "1",
                "--preview-chars",
                "79",
                "--transcript",
                str(self.transcript),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(too_low.returncode, 2)
        self.assertIn("expected at least 80", too_low.stderr)

        non_integer = subprocess.run(
            [
                sys.executable,
                str(QUERY),
                "search",
                "--term",
                "manual-fetch",
                "--limit",
                "many",
                "--transcript",
                str(self.transcript),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(non_integer.returncode, 2)
        self.assertIn("invalid parse value", non_integer.stderr)

    def test_outline_pages_genuine_user_spine(self):
        before_line = None
        items = []
        while True:
            args = ["outline", "--limit", "2", "--preview-chars", "80"]
            if before_line is not None:
                args.extend(["--before-line", str(before_line)])
            payload, output = self.run_query(*args)
            items = payload["items"] + items
            self.assertTrue(payload["input_incomplete"])
            self.assertNotIn("FORBIDDEN_", output)
            if not payload["has_more"]:
                break
            before_line = payload["next_before_line"]

        excerpts = [item.get("excerpt", "") for item in items]
        self.assertEqual(excerpts.count("Initial target: keep alpha"), 2)
        self.assertIn("Correction: use beta instead", excerpts)
        self.assertIn("Unicode check: \u4e2d\u6587", excerpts)
        self.assertNotIn("FORBIDDEN_WRAPPER", " ".join(excerpts))
        self.assertEqual(sum(item["kind"] == "compaction" for item in items), 1)

    def test_search_links_async_terminal_result_and_excludes_query_echo(self):
        payload, output = self.run_query(
            "search",
            "--term",
            "manual-fetch",
            "--term",
            "HTTP 403",
            "--limit",
            "4",
        )
        self.assertEqual(payload["total_matches"], 1)
        match = payload["matches"][0]
        self.assertEqual(match["state"], "failed")
        self.assertEqual(match["record_count"], 6)
        self.assertEqual(match["handles"], ["cell:92", "session:3407"])
        self.assertEqual(
            set(match["call_ids"]), {"call-start", "call-wait", "call-finish"}
        )
        self.assertLess(output.count("irrelevant filler"), 8)
        self.assertNotIn("call-query", output)
        self.assertTrue(payload["input_incomplete"])

    def test_show_expands_related_chain_without_unbounded_output(self):
        payload, output = self.run_query(
            "show",
            "--call-id",
            "call-start",
            "--include-related",
            "--term",
            "HTTP 403",
            "--limit",
            "8",
        )
        self.assertEqual(payload["selected"], 6)
        self.assertEqual(payload["returned"], 6)
        self.assertIn("HTTP 403", output)
        self.assertNotIn("FORBIDDEN_", output)
        self.assertNotIn("super-secret-token", output)

    def test_slice_uses_turn_id_and_redacts_forbidden_content(self):
        payload, output = self.run_query(
            "slice",
            "--turn-id",
            "turn-change",
            "--direction",
            "forward",
            "--limit",
            "32",
        )
        self.assertGreater(payload["returned"], 0)
        self.assertNotIn("FORBIDDEN_", output)
        self.assertNotIn("super-secret-token", output)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", output)
        self.assertNotIn("gAAAAA", output)
        self.assertNotIn("call-query", output)

    def test_query_echo_is_not_searchable_even_in_diagnostic_mode(self):
        payload, output = self.run_query(
            "search",
            "--term",
            "history echo",
            "--include-query-actions",
        )
        self.assertEqual(payload["total_matches"], 0)
        self.assertEqual(payload["matches"], [])
        self.assertNotIn("private query echo", output)

        diagnostic, diagnostic_output = self.run_query(
            "search",
            "--term",
            "history-query status=failed",
            "--include-query-actions",
        )
        self.assertEqual(diagnostic["total_matches"], 1)
        self.assertIn("history-query status=failed", diagnostic_output)
        self.assertNotIn("history echo", diagnostic_output)
        self.assertNotIn("cell:92", diagnostic_output)
        self.assertNotIn("session:3407", diagnostic_output)

    def test_query_echo_exclusion_survives_slice_line_boundaries(self):
        transcript = self.write_transcript(
            "query-boundary.jsonl",
            [
                call("normal", "exec", "ordinary action", "turn-query-boundary"),
                result("normal", '{"exit_code":0,"output":"ordinary"}', "turn-query-boundary"),
                call(
                    "query",
                    "exec",
                    "python3 query_session.py slice --after-line 3",
                    "turn-query-boundary",
                ),
                result(
                    "query",
                    '{"input_incomplete":false,"output":"PRIVATE_BOUNDARY_ECHO"}',
                    "turn-query-boundary",
                ),
            ],
        )
        payload, output = self.run_query_on(
            transcript,
            "slice",
            "--after-line",
            "3",
            "--direction",
            "forward",
            "--limit",
            "10",
        )
        self.assertEqual(payload["returned"], 0)
        self.assertNotIn("PRIVATE_BOUNDARY_ECHO", output)

        searched, _ = self.run_query_on(
            transcript,
            "search",
            "--term",
            "PRIVATE_BOUNDARY_ECHO",
            "--after-line",
            "3",
        )
        self.assertEqual(searched["total_matches"], 0)
        self.assertEqual(searched["matches"], [])

    def test_manual_python_history_query_is_isolated(self):
        transcript = self.write_transcript(
            "manual-query.jsonl",
            [
                call(
                    "manual-query",
                    "exec",
                    "python3 -c \"import json; open('rollout-manual.jsonl'); "
                    "print('selected')\"",
                    "turn-manual-query",
                ),
                result("manual-query", "LEAK_VALID_MANUAL_QUERY", "turn-manual-query"),
            ],
        )
        search, _ = self.run_query_on(
            transcript, "search", "--term", "LEAK_VALID_MANUAL_QUERY"
        )
        self.assertEqual(search["total_matches"], 0)

        sliced, slice_output = self.run_query_on(
            transcript,
            "slice",
            "--direction",
            "forward",
            "--limit",
            "10",
            "--preview-chars",
            "500",
        )
        self.assertEqual(sliced["returned"], 0)
        self.assertNotIn("LEAK_VALID_MANUAL_QUERY", slice_output)

    def test_powershell_and_perl_queries_are_isolated_without_hiding_rollout_files(self):
        transcript = self.write_transcript(
            "manual-query-variants.jsonl",
            [
                call(
                    "powershell-query",
                    "exec",
                    "Get-Content rollout-powershell.jsonl | ConvertFrom-Json",
                    "turn-powershell-query",
                ),
                result(
                    "powershell-query",
                    "PRIVATE_POWERSHELL_QUERY_ECHO",
                    "turn-powershell-query",
                ),
                call(
                    "perl-query",
                    "exec",
                    "perl -MJSON::PP -ne 'print if decode_json($_)' rollout-perl.jsonl",
                    "turn-perl-query",
                ),
                result("perl-query", "PRIVATE_PERL_QUERY_ECHO", "turn-perl-query"),
                call(
                    "powershell-jsondocument",
                    "exec",
                    "Get-Content rollout-jsondocument.jsonl | ForEach-Object { "
                    "[System.Text.Json.JsonDocument]::Parse($_) }",
                    "turn-powershell-jsondocument",
                ),
                result(
                    "powershell-jsondocument",
                    "PRIVATE_JSONDOCUMENT_QUERY_ECHO",
                    "turn-powershell-jsondocument",
                ),
                call(
                    "powershell-select",
                    "exec",
                    "Select-String response_item rollout-select.jsonl",
                    "turn-powershell-select",
                ),
                result(
                    "powershell-select",
                    "PRIVATE_SELECT_STRING_QUERY_ECHO",
                    "turn-powershell-select",
                ),
                call(
                    "powershell-alias-jsonnode",
                    "exec",
                    "pwsh -Command 'gc rollout-node.jsonl | % { "
                    "[System.Text.Json.Nodes.JsonNode]::Parse($_) }'",
                    "turn-powershell-alias-node",
                ),
                result(
                    "powershell-alias-jsonnode",
                    "PRIVATE_JSONNODE_QUERY_ECHO",
                    "turn-powershell-alias-node",
                ),
                call(
                    "powershell-alias-serializer",
                    "exec",
                    "pwsh -Command 'gc rollout-serializer.jsonl | % { "
                    "[System.Text.Json.JsonSerializer]::Deserialize($_) }'",
                    "turn-powershell-alias-serializer",
                ),
                result(
                    "powershell-alias-serializer",
                    "PRIVATE_SERIALIZER_QUERY_ECHO",
                    "turn-powershell-alias-serializer",
                ),
                call(
                    "powershell-alias-select",
                    "exec",
                    "pwsh -Command 'gc rollout-sls.jsonl | sls response_item'",
                    "turn-powershell-alias-select",
                ),
                result(
                    "powershell-alias-select",
                    "PRIVATE_SLS_QUERY_ECHO",
                    "turn-powershell-alias-select",
                ),
                call(
                    "javascript-helper-query",
                    "exec",
                    "const r = await tools.exec_command({\n"
                    '  "cmd": "python3 /plugin/query_session.py search --term old"\n'
                    "});\ntext(r.output);",
                    "turn-javascript-helper",
                ),
                result(
                    "javascript-helper-query",
                    "PRIVATE_JS_HELPER_ECHO",
                    "turn-javascript-helper",
                ),
                call(
                    "raw-reader",
                    "exec",
                    "cat /tmp/.codex/sessions/2026/08/04/rollout-demo.jsonl",
                    "turn-raw-reader",
                ),
                result(
                    "raw-reader",
                    {
                        "exit_code": 0,
                        "output": '{"type":"reasoning","summary":"PRIVATE_RAW_REASONING",'
                        '"encrypted_content":"PRIVATE_RAW_ENCRYPTED"}',
                    },
                    "turn-raw-reader",
                ),
                call(
                    "ordinary-rollout",
                    "exec",
                    "sed -n '1p' rollout-plan.md",
                    "turn-ordinary-rollout",
                ),
                result(
                    "ordinary-rollout",
                    {"exit_code": 0, "output": "VISIBLE_ROLLOUT_RESULT"},
                    "turn-ordinary-rollout",
                ),
                call(
                    "ordinary-application-jsonl",
                    "exec",
                    "grep response_item application.jsonl",
                    "turn-ordinary-application",
                ),
                result(
                    "ordinary-application-jsonl",
                    "VISIBLE_APPLICATION_JSONL",
                    "turn-ordinary-application",
                ),
                call(
                    "ordinary-doc-search",
                    "exec",
                    "rg -n 'query_session.py search' README.md",
                    "turn-ordinary-doc-search",
                ),
                result(
                    "ordinary-doc-search",
                    "VISIBLE_DOC_SEARCH",
                    "turn-ordinary-doc-search",
                ),
                call(
                    "ordinary-raw-doc-printf",
                    "exec",
                    "printf 'cat /tmp/.codex/sessions/demo/rollout-x.jsonl is documented'",
                    "turn-ordinary-raw-doc",
                ),
                result(
                    "ordinary-raw-doc-printf",
                    "VISIBLE_RAW_DOC",
                    "turn-ordinary-raw-doc",
                ),
                call(
                    "ordinary-raw-doc-rg",
                    "exec",
                    "rg -n 'cat /tmp/.codex/sessions/demo/rollout-x.jsonl' README.md",
                    "turn-ordinary-raw-rg",
                ),
                result(
                    "ordinary-raw-doc-rg",
                    "VISIBLE_RAW_RG_DOC",
                    "turn-ordinary-raw-rg",
                ),
            ],
        )
        for hidden_echo in (
            "PRIVATE_POWERSHELL_QUERY_ECHO",
            "PRIVATE_PERL_QUERY_ECHO",
            "PRIVATE_JSONDOCUMENT_QUERY_ECHO",
            "PRIVATE_SELECT_STRING_QUERY_ECHO",
            "PRIVATE_JSONNODE_QUERY_ECHO",
            "PRIVATE_SERIALIZER_QUERY_ECHO",
            "PRIVATE_SLS_QUERY_ECHO",
            "PRIVATE_JS_HELPER_ECHO",
            "PRIVATE_RAW_REASONING",
            "PRIVATE_RAW_ENCRYPTED",
        ):
            payload, _ = self.run_query_on(
                transcript, "search", "--term", hidden_echo
            )
            self.assertEqual(payload["total_matches"], 0)
            self.assertEqual(payload["matches"], [])

        for visible_term in (
            "VISIBLE_ROLLOUT_RESULT",
            "VISIBLE_APPLICATION_JSONL",
            "VISIBLE_DOC_SEARCH",
            "VISIBLE_RAW_DOC",
            "VISIBLE_RAW_RG_DOC",
        ):
            visible, _ = self.run_query_on(
                transcript, "search", "--term", visible_term
            )
            self.assertEqual(visible["total_matches"], 1)

    def test_search_cursor_does_not_split_call_result_pairs(self):
        transcript = Path(self.temp_dir.name) / "pagination.jsonl"
        records = []
        for index in range(6):
            turn_id = f"turn-{index}"
            records.append(call(f"pair-{index}", "exec", f"needle operation {index}", turn_id))
            records.append(result(f"pair-{index}", '{"exit_code":0,"output":"needle ok"}', turn_id))
        with transcript.open("w", encoding="utf-8") as handle:
            for index, item in enumerate(records):
                item["timestamp"] = f"2026-08-04T01:00:{index:02d}.000Z"
                handle.write(json.dumps(item) + "\n")

        before_line = None
        call_ids = []
        while True:
            args = ["search", "--term", "needle", "--limit", "2"]
            if before_line is not None:
                args.extend(["--cursor-before-line", str(before_line)])
            payload, _ = self.run_query_on(transcript, *args)
            for match in payload["matches"]:
                self.assertEqual(match["record_count"], 2)
                call_ids.extend(match["call_ids"])
            if not payload["has_more"]:
                break
            before_line = payload["next_cursor_before_line"]

        self.assertEqual(len(call_ids), 6)
        self.assertEqual(len(set(call_ids)), 6)

    def test_context_compacted_fallback_advances_window_once(self):
        transcript = Path(self.temp_dir.name) / "fallback-boundary.jsonl"
        records = [
            message("user", "before fallback", "turn-before"),
            event("user", "before fallback"),
            {"type": "event_msg", "payload": {"type": "context_compacted"}},
            message("user", "after fallback", "turn-after"),
            event("user", "after fallback"),
        ]
        with transcript.open("w", encoding="utf-8") as handle:
            for index, item in enumerate(records):
                item["timestamp"] = f"2026-08-04T02:00:{index:02d}.000Z"
                handle.write(json.dumps(item) + "\n")

        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "10",
        )
        items = payload["items"]
        before = next(item for item in items if item.get("excerpt") == "before fallback")
        boundary = next(item for item in items if item["kind"] == "compaction")
        after = next(item for item in items if item.get("excerpt") == "after fallback")
        self.assertEqual(before["window"], 0)
        self.assertEqual(boundary["window"], 1)
        self.assertEqual(after["window"], 1)

    def test_substantive_records_close_top_level_compaction_mirror_window(self):
        transcript = self.write_transcript(
            "separate-fallback-boundary.jsonl",
            [
                {"type": "compacted", "payload": {"message": "first summary"}},
                message("user", "work after first boundary", "turn-one"),
                event("user", "work after first boundary"),
                message("assistant", "continuing work", "turn-one", "commentary"),
                event("assistant", "continuing work"),
                call("between", "exec", "observable action", "turn-one"),
                result("between", '{"exit_code":0,"output":"done"}', "turn-one"),
                {"type": "event_msg", "payload": {"type": "context_compacted"}},
                message("user", "after second boundary", "turn-two"),
                event("user", "after second boundary"),
            ],
        )
        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "20",
        )
        boundaries = [item for item in payload["items"] if item["kind"] == "compaction"]
        self.assertEqual(
            [(item["line"], item["window"]) for item in boundaries],
            [(1, 1), (8, 2)],
        )
        after = next(
            item for item in payload["items"] if item.get("excerpt") == "after second boundary"
        )
        self.assertEqual(after["window"], 2)

    def test_telemetry_does_not_split_a_delayed_compaction_mirror(self):
        records = [{"type": "compacted", "payload": {"message": "summary"}}]
        records.extend(
            {
                "type": "event_msg",
                "payload": {"type": "token_count", "value": index},
            }
            for index in range(8)
        )
        records.extend(
            [
                {"type": "event_msg", "payload": {"type": "context_compacted"}},
                message("user", "after delayed mirror", "turn-after-mirror"),
                event("user", "after delayed mirror"),
            ]
        )
        transcript = self.write_transcript("delayed-boundary-mirror.jsonl", records)
        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "20",
        )
        boundaries = [item for item in payload["items"] if item["kind"] == "compaction"]
        self.assertEqual([(item["line"], item["window"]) for item in boundaries], [(1, 1)])
        after = next(
            item for item in payload["items"] if item.get("excerpt") == "after delayed mirror"
        )
        self.assertEqual(after["window"], 1)

    def test_hidden_response_items_do_not_split_a_compaction_mirror(self):
        transcript = self.write_transcript(
            "hidden-response-boundary-mirror.jsonl",
            [
                {"type": "compacted", "payload": {"message": "summary"}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"text": "FORBIDDEN_HIDDEN_TELEMETRY"}],
                    },
                },
                {"type": "event_msg", "payload": {"type": "context_compacted"}},
                message("user", "after hidden response", "turn-after-hidden"),
                event("user", "after hidden response"),
            ],
        )
        payload, output = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "20",
        )
        boundaries = [item for item in payload["items"] if item["kind"] == "compaction"]
        self.assertEqual([(item["line"], item["window"]) for item in boundaries], [(1, 1)])
        after = next(
            item for item in payload["items"] if item.get("excerpt") == "after hidden response"
        )
        self.assertEqual(after["window"], 1)
        self.assertNotIn("FORBIDDEN_HIDDEN_TELEMETRY", output)

    def test_unknown_substantive_response_item_closes_a_compaction_mirror(self):
        transcript = self.write_transcript(
            "unknown-action-boundary.jsonl",
            [
                {"type": "compacted", "payload": {"message": "summary"}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "web_search_call",
                        "id": "search-action",
                        "status": "completed",
                    },
                },
                {"type": "event_msg", "payload": {"type": "context_compacted"}},
                message("user", "after unknown action", "turn-after-action"),
                event("user", "after unknown action"),
            ],
        )
        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "20",
        )
        boundaries = [item for item in payload["items"] if item["kind"] == "compaction"]
        self.assertEqual(
            [(item["line"], item["window"]) for item in boundaries],
            [(1, 1), (3, 2)],
        )
        after = next(
            item for item in payload["items"] if item.get("excerpt") == "after unknown action"
        )
        self.assertEqual(after["window"], 2)

    def test_redacts_common_plain_and_structured_credentials(self):
        transcript = self.write_transcript(
            "credentials.jsonl",
            [
                call(
                    "secret-call",
                    "exec",
                    "Authorization: Basic dXNlcjpwYXNz\n"
                    'log={"password":"two words secret"}\n'
                    "aws_secret_access_key=AWS-PLAIN-SECRET\n"
                    "GITHUB_TOKEN=GITHUB-NAMESPACED OPENAI_API_KEY=OPENAI-NAMESPACED "
                    "MY_PASSWORD=MY-NAMESPACED\n"
                    "tool --password hunter2 --token generic-token-value "
                    "--api-key GenericKey123 --client-secret 'quoted client secret' "
                    "--access-token ACCESS-TOKEN --github-token GITHUB-CLI "
                    "-Password POWERSHELL-PASSWORD /Password WINDOWS-PASSWORD "
                    "--user alice:CURL-PASSWORD --user bob:CURL-PLAIN --mode safe\n"
                    "curl -uattached:CURL-ATTACHED https://host "
                    "--proxy-user proxy:CURL-PROXY "
                    "--oauth2-bearer CURL-BEARER\n"
                    "password NETRC-PASSWORD password\tNETRC-TAB token PLAIN-TOKEN\n"
                    "Authorization => Bearer HEADER-ARROW\n"
                    "Cookie: sessionid=COOKIE-HEADER; csrf=COOKIE-SECOND\n"
                    "postgresql://alice:URI-PASSWORD@db.example.test/app "
                    "https://TOKEN-ONLY@host/path //alice:URI-RELATIVE@host/path",
                    "turn-secret",
                ),
                result(
                    "secret-call",
                    {
                        "aws_secret_access_key": "AWS-STRUCTURED-SECRET",
                        "nested": {"clientSecret": "client value with spaces"},
                        "auth": "alice:STRUCT-AUTH",
                        "cookie": "STRUCTURED-COOKIE",
                        "endpoint": "https://alice:STRUCTURED-URI@api.example.test",
                        "userpwd": "alice:STRUCT-USERPWD",
                        "visible": "keep-me",
                    },
                    "turn-secret",
                ),
                call(
                    "isolated-secret-call",
                    "exec",
                    "//alice:SCHEME-RELATIVE@host/path\n"
                    "curl --pass CLI-PASS https://host\n"
                    "db.pass=DB-DOTTED-PASS access_key_id=ACCESS-KEY-ID\n"
                    "DB_PASS DB-SPACE-PASS db.pass DB-DOTTED-SPACE\n"
                    "access_key_id ACCESS-ID-SPACE AWS_ACCESS_KEY_ID AWS-ACCESS-SPACE\n"
                    "X-Auth: X-AUTH-VALUE\n"
                    "Authorization Bearer HEADER-SPACE-BEARER\n"
                    "Authorization: Negotiate HEADER-NEGOTIATE\n"
                    'user = "alice:CURL-CONFIG-PASS"',
                    "turn-secret",
                ),
                result(
                    "isolated-secret-call",
                    {
                        "token_count": 42,
                        "authorization_status": "ready",
                        "visible": "keep-status-fields",
                    },
                    "turn-secret",
                ),
            ],
        )
        _, output = self.run_query_on(
            transcript,
            "show",
            "--turn-id",
            "turn-secret",
            "--limit",
            "12",
            "--preview-chars",
            "2000",
        )
        for secret in (
            "dXNlcjpwYXNz",
            "two words secret",
            "AWS-PLAIN-SECRET",
            "AWS-STRUCTURED-SECRET",
            "client value with spaces",
            "hunter2",
            "generic-token-value",
            "GenericKey123",
            "quoted client secret",
            "GITHUB-NAMESPACED",
            "OPENAI-NAMESPACED",
            "MY-NAMESPACED",
            "ACCESS-TOKEN",
            "GITHUB-CLI",
            "POWERSHELL-PASSWORD",
            "WINDOWS-PASSWORD",
            "CURL-PASSWORD",
            "CURL-PLAIN",
            "CURL-ATTACHED",
            "CURL-PROXY",
            "CURL-BEARER",
            "NETRC-PASSWORD",
            "NETRC-TAB",
            "PLAIN-TOKEN",
            "HEADER-ARROW",
            "COOKIE-HEADER",
            "COOKIE-SECOND",
            "URI-PASSWORD",
            "STRUCTURED-COOKIE",
            "STRUCTURED-URI",
            "TOKEN-ONLY",
            "URI-RELATIVE",
            "STRUCT-AUTH",
            "STRUCT-USERPWD",
            "SCHEME-RELATIVE",
            "CLI-PASS",
            "DB-DOTTED-PASS",
            "ACCESS-KEY-ID",
            "DB-SPACE-PASS",
            "DB-DOTTED-SPACE",
            "ACCESS-ID-SPACE",
            "AWS-ACCESS-SPACE",
            "X-AUTH-VALUE",
            "HEADER-SPACE-BEARER",
            "HEADER-NEGOTIATE",
            "CURL-CONFIG-PASS",
        ):
            self.assertNotIn(secret, output)
        self.assertIn("[REDACTED]", output)
        self.assertIn("keep-me", output)
        self.assertIn("--mode safe", output)
        self.assertIn("token_count", output)
        self.assertIn("authorization_status", output)
        self.assertIn("keep-status-fields", output)

    def test_hidden_and_unknown_content_blocks_fail_closed(self):
        transcript = self.write_transcript(
            "hidden-tool-output.jsonl",
            [
                call("hidden-dict", "exec", "inspect direct block", "turn-hidden"),
                result(
                    "hidden-dict",
                    {"type": "reasoning", "text": "FORBIDDEN_DIRECT_REASONING"},
                    "turn-hidden",
                ),
                call("hidden-mixed", "exec", "inspect mixed blocks", "turn-hidden"),
                result(
                    "hidden-mixed",
                    [
                        {"type": "reasoning", "text": "FORBIDDEN_MIXED_REASONING"},
                        {"malformed": "FORBIDDEN_MALFORMED_FALLBACK"},
                    ],
                    "turn-hidden",
                ),
                call("hidden-string", "exec", "inspect encoded block", "turn-hidden"),
                result(
                    "hidden-string",
                    '{"type":"reasoning","text":"FORBIDDEN_STRING_REASONING"}',
                    "turn-hidden",
                ),
                call("hidden-nested", "exec", "inspect nested block", "turn-hidden"),
                result(
                    "hidden-nested",
                    {
                        "visible": "keep-visible",
                        "reasoningSummary": "FORBIDDEN_CAMEL_REASONING",
                        "replacementHistory": ["FORBIDDEN_CAMEL_HISTORY"],
                        "payload": {
                            "type": "mystery_block",
                            "content": "FORBIDDEN_UNKNOWN_CONTENT",
                        },
                        "delta": {
                            "type": "reasoning_delta",
                            "delta": "FORBIDDEN_REASONING_DELTA",
                        },
                        "futureData": {
                            "type": "future_reasoning",
                            "data": "FORBIDDEN_UNKNOWN_DATA",
                        },
                        "futurePayload": {
                            "type": "future_reasoning",
                            "payload": {"value": "FORBIDDEN_UNKNOWN_PAYLOAD"},
                        },
                        "numericType": {
                            "type": 7,
                            "content": "FORBIDDEN_NUMERIC_TYPE",
                        },
                        "caseVariant": {
                            "Type": "future_reasoning",
                            "data": "FORBIDDEN_CAPITAL_TYPE",
                        },
                        "unknownContent": {
                            "type": "mystery",
                            "content": "FORBIDDEN_MYSTERY_CONTENT",
                        },
                        "unknownData": {
                            "type": "future_data",
                            "data": "FORBIDDEN_FUTURE_DATA",
                        },
                        "domain": {"type": "invoice", "id": "INV-42", "status": "paid"},
                        "domainStatus": {
                            "type": "message_queue_status",
                            "queue": "jobs",
                            "count": 2,
                        },
                    },
                    "turn-hidden",
                ),
                call("hidden-message", "exec", "inspect alternate block", "turn-hidden"),
                result(
                    "hidden-message",
                    {"type": "mystery_block", "message": "FORBIDDEN_UNKNOWN_MESSAGE"},
                    "turn-hidden",
                ),
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": "FORBIDDEN_RAW_MESSAGE_CONTENT",
                        "internal_chat_message_metadata_passthrough": {
                            "turn_id": "turn-hidden"
                        },
                    },
                },
            ],
        )
        _, output = self.run_query_on(
            transcript,
            "slice",
            "--turn-id",
            "turn-hidden",
            "--direction",
            "forward",
            "--limit",
            "32",
        )
        self.assertNotIn("FORBIDDEN_", output)
        self.assertIn("keep-visible", output)
        self.assertIn("INV-42", output)
        self.assertIn("message_queue_status", output)

        search, _ = self.run_query_on(
            transcript, "search", "--term", "FORBIDDEN", "--limit", "4"
        )
        self.assertEqual(search["total_matches"], 0)

    def test_show_handle_and_turn_do_not_select_query_echoes(self):
        transcript = self.write_transcript(
            "query-selection.jsonl",
            [
                call("normal", "exec", "ordinary action", "turn-query"),
                result("normal", '{"exit_code":0,"output":"ordinary result"}', "turn-query"),
                call(
                    "query",
                    "exec",
                    "python3 query_session.py search --term private",
                    "turn-query",
                ),
                result(
                    "query",
                    '{"error":"PRIVATE_QUERY_ECHO cell_id:777","incomplete":true}',
                    "turn-query",
                ),
            ],
        )
        by_handle, handle_output = self.run_query_on(
            transcript, "show", "--handle", "cell:777"
        )
        self.assertEqual(by_handle["selected"], 0)
        self.assertNotIn("PRIVATE_QUERY_ECHO", handle_output)

        by_turn, turn_output = self.run_query_on(
            transcript, "show", "--turn-id", "turn-query", "--limit", "12"
        )
        self.assertEqual(by_turn["selected"], 2)
        self.assertIn("ordinary result", turn_output)
        self.assertNotIn("PRIVATE_QUERY_ECHO", turn_output)

        explicit, explicit_output = self.run_query_on(
            transcript,
            "show",
            "--call-id",
            "query",
            "--include-related",
            "--limit",
            "12",
        )
        self.assertEqual(explicit["selected"], 2)
        self.assertTrue(all(item["diagnostic_only"] for item in explicit["items"]))
        self.assertIn("history-query status=failed", explicit_output)
        self.assertNotIn("PRIVATE_QUERY_ECHO", explicit_output)
        self.assertNotIn("cell:777", explicit_output)

    def test_mirror_messages_do_not_merge_across_compaction_windows(self):
        transcript = self.write_transcript(
            "cross-window-mirror.jsonl",
            [
                message("user", "same visible request", "turn-before"),
                {"type": "compacted", "payload": {"message": "summary"}},
                event("user", "same visible request"),
            ],
        )
        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "10",
        )
        items = [
            item for item in payload["items"] if item.get("excerpt") == "same visible request"
        ]
        self.assertEqual(
            [(item["line"], item["window"]) for item in items],
            [(1, 0), (3, 1)],
        )
        self.assertTrue(all("aliases" not in item for item in items))

    def test_repeated_message_mirror_prefers_latest_preceding_response(self):
        transcript = self.write_transcript(
            "nearest-message-mirror.jsonl",
            [
                message("user", "same request", "turn-old"),
                message("user", "same request", "turn-new"),
                event("user", "same request"),
            ],
        )
        payload, _ = self.run_query_on(
            transcript,
            "slice",
            "--direction",
            "forward",
            "--limit",
            "10",
        )
        items = [item for item in payload["items"] if item["kind"] == "user"]
        self.assertEqual(
            [(item["line"], item.get("turn_id"), item.get("aliases")) for item in items],
            [(1, "turn-old", None), (2, "turn-new", [2, 3])],
        )

    def test_only_nearest_synthesized_precompaction_assistant_is_removed(self):
        repeated = "Repeated assistant summary text"
        transcript = self.write_transcript(
            "synthetic-summary.jsonl",
            [
                message("assistant", repeated, "turn-old", "commentary"),
                event("assistant", repeated),
                message("assistant", repeated, "turn-nearest", "commentary"),
                event("assistant", repeated),
                {
                    "type": "compacted",
                    "payload": {
                        "message": f"Native compacted summary contains: {repeated}",
                        "replacement_history": ["FORBIDDEN_REPLACEMENT"],
                    },
                },
            ],
        )
        payload, output = self.run_query_on(
            transcript,
            "search",
            "--term",
            repeated,
            "--include-messages",
            "--limit",
            "4",
        )
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["matches"][0]["anchor_line"], 1)
        self.assertNotIn("Native compacted summary", output)
        self.assertNotIn("FORBIDDEN_REPLACEMENT", output)

    def test_async_component_crosses_turns_with_opaque_cell_handle(self):
        records = [
            call("start", "exec", "needle cross-turn action", "turn-a"),
            result("start", "Script running with cell ID job-abc.7", "turn-a"),
            call("finish", "wait", '{"cell_id":"job-abc.7"}', "turn-b", custom=False),
            result(
                "finish",
                '{"exit_code":0,"output":"done"}',
                "turn-b",
                custom=False,
            ),
        ]
        transcript = self.write_transcript("cross-turn-async.jsonl", records)
        payload, _ = self.run_query_on(transcript, "search", "--term", "needle")
        self.assertEqual(payload["total_matches"], 1)
        match = payload["matches"][0]
        self.assertEqual(match["record_count"], 4)
        self.assertEqual(match["state"], "succeeded")
        self.assertEqual(match["handles"], ["cell:job-abc.7"])
        self.assertEqual(match["turn_ids"], ["turn-a", "turn-b"])

        trailing = self.write_transcript(
            "cross-turn-unpaired.jsonl",
            records
            + [
                call(
                    "trailing",
                    "wait",
                    '{"cell_id":"job-abc.7"}',
                    "turn-c",
                    custom=False,
                )
            ],
        )
        trailing_payload, _ = self.run_query_on(
            trailing, "search", "--term", "needle"
        )
        trailing_match = trailing_payload["matches"][0]
        self.assertEqual(trailing_match["state"], "unpaired")
        self.assertIn("trailing", trailing_match["unpaired_call_ids"])

    def test_uuid_session_id_is_not_treated_as_numeric_async_handle(self):
        transcript = self.write_transcript(
            "uuid-session-id.jsonl",
            [
                call("uuid", "exec", "needle uuid metadata", "turn-uuid"),
                result(
                    "uuid",
                    '{"session_id":"019fbca2-8ca8-7563-a113-fd3889a0f87c",'
                    '"exit_code":0,"output":"done"}',
                    "turn-uuid",
                ),
            ],
        )
        payload, output = self.run_query_on(transcript, "search", "--term", "needle")
        self.assertEqual(payload["matches"][0]["handles"], [])
        self.assertNotIn("session:019", output)

    def test_running_async_chain_can_continue_across_compaction(self):
        transcript = self.write_transcript(
            "cross-window-continuation.jsonl",
            [
                call("start", "exec", "CROSS_WINDOW_NEEDLE", "turn-start"),
                result("start", "Script running with cell ID durable-job", "turn-start"),
                {"type": "compacted", "payload": {"message": "boundary"}},
                call(
                    "finish",
                    "wait",
                    '{"cell_id":"durable-job"}',
                    "turn-finish",
                    custom=False,
                ),
                result(
                    "finish",
                    {"exit_code": 0, "output": "done after compaction"},
                    "turn-finish",
                    custom=False,
                ),
            ],
        )
        payload, _ = self.run_query_on(
            transcript, "search", "--term", "CROSS_WINDOW_NEEDLE"
        )
        self.assertEqual(payload["total_matches"], 1)
        match = payload["matches"][0]
        self.assertEqual(match["record_count"], 4)
        self.assertEqual(match["state"], "succeeded")
        self.assertEqual(match["windows"], [0, 1])

        bounded, _ = self.run_query_on(
            transcript,
            "search",
            "--term",
            "CROSS_WINDOW_NEEDLE",
            "--before-line",
            "3",
        )
        self.assertEqual(bounded["total_matches"], 1)
        bounded_match = bounded["matches"][0]
        self.assertEqual(bounded_match["record_count"], 2)
        self.assertEqual(bounded_match["state"], "running")
        self.assertEqual(bounded_match["windows"], [0])

    def test_async_handles_do_not_join_across_compaction_windows(self):
        transcript = self.write_transcript(
            "window-handle-reuse.jsonl",
            [
                call("root-start", "exec", "PREBOUND_NEEDLE", "turn-root"),
                result("root-start", "Script running with cell ID shared-job", "turn-root"),
                call(
                    "root-wait",
                    "wait",
                    '{"cell_id":"shared-job"}',
                    "turn-root",
                    custom=False,
                ),
                result(
                    "root-wait",
                    {"exit_code": 1},
                    "turn-root",
                    custom=False,
                ),
                {"type": "compacted", "payload": {"message": "boundary"}},
                call("nested-start", "exec", "unrelated", "turn-nested"),
                result(
                    "nested-start",
                    "Script running with cell ID shared-job",
                    "turn-nested",
                ),
                call(
                    "nested-wait",
                    "wait",
                    '{"cell_id":"shared-job"}',
                    "turn-nested",
                    custom=False,
                ),
                result(
                    "nested-wait",
                    {"exit_code": 0},
                    "turn-nested",
                    custom=False,
                ),
            ],
        )
        bounded, _ = self.run_query_on(
            transcript,
            "search",
            "--term",
            "PREBOUND_NEEDLE",
            "--before-line",
            "5",
        )
        self.assertEqual(bounded["total_matches"], 1)
        self.assertEqual(bounded["matches"][0]["record_count"], 4)
        self.assertEqual(bounded["matches"][0]["state"], "failed")

        unbounded, _ = self.run_query_on(
            transcript, "search", "--term", "PREBOUND_NEEDLE"
        )
        self.assertEqual(unbounded["total_matches"], 1)
        self.assertEqual(unbounded["matches"][0]["record_count"], 4)
        self.assertEqual(unbounded["matches"][0]["state"], "failed")

    def test_show_call_id_cursor_keeps_original_chain_anchor(self):
        records = [
            call("start-show", "exec", "needle paged chain", "turn-show-chain"),
            result(
                "start-show",
                "Script running with cell ID job-show.1",
                "turn-show-chain",
            ),
        ]
        for index in range(1, 5):
            call_id = f"continue-{index}"
            records.append(
                call(
                    call_id,
                    "wait",
                    '{"cell_id":"job-show.1"}',
                    f"turn-show-chain-{index}",
                    custom=False,
                )
            )
            output = (
                '{"exit_code":0,"output":"done"}'
                if index == 4
                else '{"session_id":3407,"chunk_id":"chunk",'
                '"wall_time_seconds":1,"output":""}'
            )
            records.append(
                result(
                    call_id,
                    output,
                    f"turn-show-chain-{index}",
                    custom=False,
                )
            )
        transcript = self.write_transcript("show-call-cursor.jsonl", records)

        after_line = None
        lines = []
        for _ in range(5):
            args = [
                "show",
                "--call-id",
                "start-show",
                "--include-related",
                "--limit",
                "4",
            ]
            if after_line is not None:
                args.extend(["--after-line", str(after_line)])
            payload, _ = self.run_query_on(transcript, *args)
            lines.extend(item["line"] for item in payload["items"])
            if not payload["has_more"]:
                break
            self.assertIn("next_after_line", payload)
            after_line = payload["next_after_line"]
        self.assertEqual(lines, list(range(1, 11)))

    def test_structured_status_uses_only_outer_truthy_failure_fields(self):
        cases = [
            ("null-error", {"error": None, "output": "ok"}, "completed-unverified"),
            ("false-error", {"error": False, "output": "ok"}, "completed-unverified"),
            (
                "nested-error",
                {"payload": {"exit_code": 1, "error": "nested failure"}, "output": "ok"},
                "completed-unverified",
            ),
            (
                "nested-completed-text",
                {
                    "output": "Script completed successfully",
                    "meta": {"exit_code": 7, "status": "failed", "error": "nested"},
                },
                "completed-unverified",
            ),
            ("in-progress", {"status": "in_progress"}, "running"),
            ("incomplete", {"status": "incomplete"}, "running"),
            ("requires-action", {"status": "requires_action"}, "running"),
            ("paused", {"status": "paused"}, "running"),
            ("pending", {"status": "pending"}, "running"),
            ("queued", {"status": "queued"}, "running"),
            ("expired", {"status": "expired"}, "failed"),
            ("cancelled", {"status": "cancelled"}, "failed"),
            ("failure", {"status": "failure"}, "failed"),
            ("success", {"status": "success"}, "succeeded"),
            ("outer-error", {"error": "outer failure"}, "failed"),
            ("outer-exit", {"exit_code": 0, "error": "ignored"}, "succeeded"),
        ]
        records = []
        for name, output, _ in cases:
            records.extend(
                [
                    call(name, "exec", f"needle-status-{name}", f"turn-{name}"),
                    result(name, output, f"turn-{name}"),
                ]
            )
        transcript = self.write_transcript("structured-status.jsonl", records)
        for name, _, expected in cases:
            payload, _ = self.run_query_on(
                transcript,
                "search",
                "--term",
                f"needle-status-{name}",
                "--limit",
                "4",
            )
            self.assertEqual(payload["total_matches"], 1)
            self.assertEqual(payload["matches"][0]["state"], expected)

    def test_result_payload_status_is_used_for_component_state(self):
        transcript = self.write_transcript(
            "payload-status.jsonl",
            [
                call("payload-running", "exec", "PAYLOAD_STATUS_NEEDLE", "turn-status"),
                result(
                    "payload-running",
                    "still working",
                    "turn-status",
                    status="in_progress",
                ),
            ],
        )
        payload, _ = self.run_query_on(
            transcript, "search", "--term", "PAYLOAD_STATUS_NEEDLE"
        )
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["matches"][0]["state"], "running")

    def test_search_pages_interleaved_async_components(self):
        transcript = self.write_transcript(
            "interleaved.jsonl",
            [
                call("outer-start", "exec", "needle outer", "turn-outer"),
                result("outer-start", "Script running with cell ID outer-job", "turn-outer"),
                call("inner", "exec", "needle inner", "turn-inner"),
                result("inner", '{"exit_code":0,"output":"inner done"}', "turn-inner"),
                call(
                    "outer-finish",
                    "wait",
                    '{"cell_id":"outer-job"}',
                    "turn-outer",
                    custom=False,
                ),
                result(
                    "outer-finish",
                    '{"exit_code":0,"output":"outer done"}',
                    "turn-outer",
                    custom=False,
                ),
            ],
        )
        before_line = None
        matches = []
        while True:
            args = ["search", "--term", "needle", "--limit", "1"]
            if before_line is not None:
                args.extend(["--cursor-before-line", str(before_line)])
            payload, _ = self.run_query_on(transcript, *args)
            matches.extend(payload["matches"])
            if not payload["has_more"]:
                break
            before_line = payload["next_cursor_before_line"]

        self.assertEqual([match["anchor_line"] for match in matches], [6, 4])
        self.assertEqual([match["record_count"] for match in matches], [4, 2])

    def test_byte_limited_pages_keep_every_record_reachable(self):
        outline_records = []
        for index in range(64):
            text = f"message-{index:02d}-" + ("\u4e2d" * 300)
            outline_records.extend(
                [message("user", text, f"turn-{index}"), event("user", text)]
            )
        transcript = self.write_transcript("large-outline.jsonl", outline_records)
        expected_lines = set(range(1, 128, 2))

        for direction in ("forward", "backward"):
            cursor = None
            seen = []
            for _ in range(100):
                args = [
                    "outline",
                    "--direction",
                    direction,
                    "--limit",
                    "64",
                    "--preview-chars",
                    "320",
                ]
                if cursor is not None:
                    flag = "--after-line" if direction == "forward" else "--before-line"
                    args.extend([flag, str(cursor)])
                payload, _ = self.run_query_on(transcript, *args)
                seen.extend(item["line"] for item in payload["items"])
                if not payload["has_more"]:
                    break
                key = "next_after_line" if direction == "forward" else "next_before_line"
                self.assertIn(key, payload)
                cursor = payload[key]
            else:
                self.fail(f"{direction} outline pagination did not terminate")
            self.assertEqual(set(seen), expected_lines)
            self.assertEqual(len(seen), len(expected_lines))

    def test_search_byte_trim_creates_reachable_cursor(self):
        records = []
        for index in range(5):
            call_id = f"pair-{index}-" + ("x" * 1000)
            records.extend(
                [
                    call(call_id, "exec", f"needle operation {index}", f"turn-{index}"),
                    result(
                        call_id,
                        '{"exit_code":0,"output":"needle done"}',
                        f"turn-{index}",
                    ),
                ]
            )
        transcript = self.write_transcript("large-search.jsonl", records)
        before_line = None
        anchors = []
        saw_output_limit = False
        for _ in range(10):
            args = ["search", "--term", "needle", "--limit", "12"]
            if before_line is not None:
                args.extend(["--cursor-before-line", str(before_line)])
            payload, _ = self.run_query_on(transcript, *args)
            anchors.extend(match["anchor_line"] for match in payload["matches"])
            saw_output_limit = saw_output_limit or payload.get("output_limited", False)
            if not payload["has_more"]:
                break
            self.assertIn("next_cursor_before_line", payload)
            before_line = payload["next_cursor_before_line"]
        self.assertTrue(saw_output_limit)
        self.assertEqual(anchors, [10, 8, 6, 4, 2])

    def test_show_byte_trim_emits_next_after_line(self):
        records = []
        for index in range(12):
            text = f"assistant-{index:02d}-" + ("x" * 1800)
            records.extend(
                [
                    message("assistant", text, "turn-show", "commentary"),
                    event("assistant", text),
                ]
            )
        transcript = self.write_transcript("large-show.jsonl", records)
        after_line = None
        lines = []
        for _ in range(10):
            args = [
                "show",
                "--turn-id",
                "turn-show",
                "--limit",
                "12",
                "--preview-chars",
                "2000",
            ]
            if after_line is not None:
                args.extend(["--after-line", str(after_line)])
            payload, _ = self.run_query_on(transcript, *args)
            lines.extend(item["line"] for item in payload["items"])
            if not payload["has_more"]:
                break
            self.assertIn("next_after_line", payload)
            after_line = payload["next_after_line"]
        self.assertEqual(lines, list(range(1, 24, 2)))

    def test_single_oversize_search_projection_uses_bounded_stub(self):
        call_id = "oversize-" + ("z" * 20000)
        transcript = self.write_transcript(
            "oversize-candidate.jsonl",
            [
                call(call_id, "exec", "needle oversized", "turn-oversize"),
                result(call_id, '{"exit_code":0,"output":"needle done"}', "turn-oversize"),
            ],
        )
        payload, _ = self.run_query_on(transcript, "search", "--term", "needle")
        self.assertTrue(payload["projection_limited"])
        self.assertTrue(payload["matches"][0]["projection_limited"])
        self.assertEqual(payload["matches"][0]["anchor_line"], 2)

    def test_maximum_multibyte_search_terms_keep_match_and_anchor(self):
        terms = [f"T{index}" + ("\u4e2d" * 254) for index in range(8)]
        transcript = self.write_transcript(
            "multibyte-terms.jsonl",
            [
                call("multibyte", "exec", " ".join(terms), "turn-multibyte"),
                result(
                    "multibyte",
                    {"exit_code": 0, "output": "done"},
                    "turn-multibyte",
                ),
            ],
        )
        args = ["search"]
        for term in terms:
            args.extend(["--term", term])
        payload, _ = self.run_query_on(transcript, *args)
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["matches"][0]["anchor_line"], 2)
        self.assertNotIn("error", payload)

    def test_many_identical_mirrors_remain_distinct_and_deduplicated(self):
        records = []
        for index in range(5000):
            records.extend(
                [
                    message("user", "same repeated request", f"repeat-{index}"),
                    event("user", "same repeated request"),
                ]
            )
        transcript = self.write_transcript("many-mirrors.jsonl", records)
        payload, _ = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "backward",
            "--limit",
            "64",
        )
        self.assertEqual(payload["total_candidates"], 5000)
        self.assertEqual(payload["returned"], 64)

    def test_deep_structured_tool_output_is_omitted_and_marked_incomplete(self):
        deep_output = "[" * 1200 + '"PRIVATE_DEEP_VALUE"' + "]" * 1200
        transcript = self.write_transcript(
            "deep-structured-output.jsonl",
            [
                call("deep", "exec", "inspect deep output", "turn-deep"),
                result("deep", deep_output, "turn-deep"),
            ],
        )
        payload, output = self.run_query_on(
            transcript,
            "show",
            "--call-id",
            "deep",
            "--include-related",
        )
        self.assertTrue(payload["input_incomplete"])
        self.assertEqual(payload["sanitization_incomplete_lines"], [2])
        self.assertNotIn("PRIVATE_DEEP_VALUE", output)

    def test_lone_surrogate_is_emitted_as_a_valid_json_escape(self):
        transcript = Path(self.temp_dir.name) / "surrogate.jsonl"
        item = message(
            "user",
            "valid prefix " + chr(0xD800) + " suffix",
            "turn-surrogate",
        )
        item["timestamp"] = "2026-08-04T09:00:00.000Z"
        transcript.write_text(json.dumps(item, ensure_ascii=True) + "\n", encoding="ascii")
        payload, output = self.run_query_on(
            transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "4",
        )
        self.assertEqual(payload["returned"], 1)
        self.assertIn("valid prefix", payload["items"][0]["excerpt"])
        self.assertIn("\\ud800", output)

    def test_unicode_output_works_with_ascii_python_io_encoding(self):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "ascii"
        payload, _ = self.run_query_on(
            self.transcript,
            "outline",
            "--direction",
            "forward",
            "--limit",
            "64",
            env=env,
        )
        self.assertTrue(
            any("\u4e2d\u6587" in item.get("excerpt", "") for item in payload["items"])
        )


if __name__ == "__main__":
    unittest.main()
