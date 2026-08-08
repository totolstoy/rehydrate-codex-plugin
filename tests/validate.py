#!/usr/bin/env python3

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "rehydrate"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), f"Invalid frontmatter in {path}"
    return yaml.safe_load(parts[1]), text


manifest = load_json(PLUGIN / ".codex-plugin" / "plugin.json")
assert manifest["name"] == "rehydrate"
assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", manifest["version"])
assert manifest["version"] == "0.4.3"
release_version = manifest["version"].split("+", 1)[0]
assert release_version == "0.4.3"
assert manifest["license"] == "MIT"
assert manifest["skills"] == "./skills/"
assert manifest["repository"].startswith("https://github.com/")
assert "bounded structural history index" in manifest["interface"]["longDescription"]
assert "before the first retry or workaround" in manifest["interface"]["longDescription"]
assert all(len(prompt) <= 128 for prompt in manifest["interface"]["defaultPrompt"])

marketplace = load_json(ROOT / ".agents" / "plugins" / "marketplace.json")
assert marketplace["name"] == "rehydrate-marketplace"
entries = [entry for entry in marketplace["plugins"] if entry["name"] == "rehydrate"]
assert len(entries) == 1
entry = entries[0]
assert entry["source"] == {"source": "local", "path": "./plugins/rehydrate"}
assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
assert entry["category"] == "Productivity"

skill_meta, skill_text = load_frontmatter(PLUGIN / "skills" / "rehydrate" / "SKILL.md")
assert skill_meta["name"] == "rehydrate"
description = skill_meta["description"].lower()
for phrase in (
    "context compaction",
    "final meaningful pre-compaction work segment",
    "whole-session trajectory",
    "bounded structural index",
    "targeted evidence expansion",
    "during execution",
    "before the first retry or workaround",
):
    assert phrase in description, f"Missing skill description contract: {phrase}"

skill_lower = re.sub(r"\s+", " ", skill_text.lower())
for phrase in (
    "initial goal",
    "entire session",
    "later clarifications",
    "final meaningful work segment",
    "latest top-level `compacted` record",
    "exclusive end boundary",
    "compacted.payload.message",
    "nested `replacement_history`",
    "nearest preceding assistant message",
    "never remove matching text globally",
    "structurally mirrored",
    "preserve separate records",
    "genuine user request or correction",
    "paired observable calls and results",
    "no substantive user message exists after the previous compaction",
    "governing request",
    "referential",
    "fixed record count or time window",
    "transport controls",
    "immediate tail stand in for the whole task",
    "commentary and progress updates",
    "tool or function calls paired with their results",
    "commands",
    "patches and file changes",
    "test and validation results",
    "rollbacks",
    "incomplete work",
    "planned",
    "attempted",
    "executed",
    "verified",
    "deduplicate only structurally mirrored",
    "call_id",
    "do not inspect, extract, summarize, or expose hidden reasoning",
    "reasoning summaries",
    "encrypted content",
    "sidecar state file",
    "do not wait for another user message",
    "material action boundary",
    "work might repeat, overwrite, undo, or contradict",
    "material failure",
    "mandatory recovery checkpoint",
    "before the first retry or workaround",
    "return control to the model",
    "same code-mode script",
    "stable error fragments",
    "lookup is required",
    "native summary or current working context suggests an obvious fix",
    "most recent verified success",
    "revalidate mutable prerequisites",
    "expected, accepted branch",
    "predefined interpretation and next step",
    "already been queried since activation",
    "do not rescan the same key",
    "consequential external action",
    "do not continuously",
    "scripts/query_session.py",
    "codex plugin list --json",
    "positional subcommands",
    "never replace its basename",
    "outline_session.py",
    "slice_session.py",
    "search_session.py",
    "show_session.py",
    "outline 24/1..64",
    "slice 24/1..32",
    "search 4/1..12",
    "show 8/1..12",
    "values above a cap are capped",
    "omit both controls initially",
    "dedicated tool call",
    "outline",
    "slice",
    "search",
    "show",
    "index-select-expand",
    "never search or print raw jsonl objects",
    "turn_id",
    "cell_id",
    "numeric `session_id`",
    "running or yielded result is not terminal",
    "has_more",
    "needs_refinement",
    "output_limited",
    "excerpt_truncated",
    "do not solve truncation by increasing",
    "start each query stage with the helper defaults",
    "do not raise page or preview limits for initial exploration",
    "next_cursor_before_line",
    "--cursor-before-line",
    "exclusive upper bound",
    "do not self-match",
    "history-query calls and their echoed output",
):
    assert phrase in skill_lower, f"Missing skill contract: {phrase}"

agent_meta = yaml.safe_load(
    (PLUGIN / "skills" / "rehydrate" / "agents" / "openai.yaml").read_text(encoding="utf-8")
)
interface = agent_meta["interface"]
assert 25 <= len(interface["short_description"]) <= 64
assert "$rehydrate:rehydrate" in interface["default_prompt"]
assert "bounded structural index" in interface["default_prompt"]
assert "targeted evidence expansion" in interface["default_prompt"]
assert agent_meta["policy"]["allow_implicit_invocation"] is False

hooks = load_json(PLUGIN / "hooks" / "hooks.json")
assert set(hooks["hooks"]) == {"SessionStart"}
session_hooks = hooks["hooks"]["SessionStart"]
assert len(session_hooks) == 1
assert session_hooks[0]["matcher"] == "^compact$"
command_hook = session_hooks[0]["hooks"][0]
assert command_hook["type"] == "command"
assert "${PLUGIN_ROOT}" in command_hook["command"]
assert "%PLUGIN_ROOT%" in command_hook["commandWindows"]
assert command_hook["statusMessage"] == "Restoring session-wide continuity"
assert command_hook["additionalContextLimit"] == 4000

removed_scripts = (
    PLUGIN / "scripts" / "rehydrate-after-tool.sh",
    PLUGIN / "scripts" / "rehydrate-after-tool.ps1",
)
assert all(not path.exists() for path in removed_scripts)

query_helper = PLUGIN / "scripts" / "query_session.py"
assert query_helper.is_file()
assert sorted(path.name for path in (PLUGIN / "scripts").glob("*_session.py")) == [
    "query_session.py"
]
query_text = query_helper.read_text(encoding="utf-8")
for phrase in (
    "def command_outline",
    "def command_slice",
    "def command_search",
    "def command_show",
    "turn_id",
    "call_id",
    "cell_id",
    "session_id",
    "MAX_OUTPUT_BYTES",
    "replacement_history",
    "encrypted_content",
    "input_incomplete",
    "needs_refinement",
    "cursor_before_line",
    "next_cursor_before_line",
    "QUERY_COMMANDS",
    "OUTPUT_CONTROL_CONTRACTS",
    "values above the cap are capped",
    "not separate *_session.py files",
):
    assert phrase in query_text, f"Query helper missing contract: {phrase}"
assert "requests." not in query_text
assert "urllib" not in query_text

required_fallback_phrases = (
    "entire session",
    "final meaningful pre-compaction work segment",
    "latest top-level compacted record",
    "latest substantive, genuine user request or correction",
    "paired observable calls and results",
    "tail supplements rather than replaces whole-session recovery",
    "observable assistant actions",
    "planned, attempted, executed, and verified",
    "never inspect hidden reasoning",
    "material action boundaries",
    "do not wait for another user message",
    "before the first retry or workaround",
    "stable error fragments",
    "most recent verified success",
    "revalidate mutable prerequisites",
    "expected, accepted branch",
    "predefined interpretation and next step",
    "same operation, target, and error-signature key",
    "do not rescan the same key",
    "progressive history query",
    "bounded structural index",
    "scripts/query_session.py",
    "positional subcommands",
    "never *_session.py filenames",
    "outline limit 24/1..64",
    "slice 24/1..32",
    "search 4/1..12",
    "show 8/1..12",
    "values above caps are capped",
    "fixed page size is only a transport boundary",
    "exclusive cutoff",
    "cell_id/session_id",
    "echoed output",
    "start with the helper defaults",
    "do not raise page or preview limits for initial exploration",
    "next_cursor_before_line",
    "--cursor-before-line",
)

for script in ("rehydrate-on-compact.sh", "rehydrate-on-compact.ps1"):
    script_path = PLUGIN / "scripts" / script
    assert script_path.is_file()
    script_text = script_path.read_text(encoding="utf-8")
    assert "$rehydrate:rehydrate" in script_text
    assert "<name>rehydrate:rehydrate</name>" in script_text
    assert '<rehydrate-runtime version="0.4.3" />' in script_text
    assert "<skill-load-fallback>" in script_text
    for phrase in required_fallback_phrases:
        assert phrase.lower() in script_text.lower(), f"Missing fallback contract in {script}: {phrase}"
    assert "complete skill body is embedded below and is already loaded" in script_text
    assert "do not open or resolve a cached skill.md locator" in script_text.lower()
    assert "posttooluse" not in script_text.lower()
    assert "post-tool-checkpoint" not in script_text.lower()

assert "${PLUGIN_ROOT:-}" in (PLUGIN / "scripts" / "rehydrate-on-compact.sh").read_text(encoding="utf-8")
assert "$env:PLUGIN_ROOT" in (PLUGIN / "scripts" / "rehydrate-on-compact.ps1").read_text(encoding="utf-8")

payload = '{"source":"compact","session_id":"test"}'
hook_env = os.environ.copy()
hook_env["PLUGIN_ROOT"] = str(PLUGIN)
posix_hook = PLUGIN / "scripts" / "rehydrate-on-compact.sh"
hook_result = subprocess.run(
    ["sh", str(posix_hook)],
    input=payload,
    text=True,
    capture_output=True,
    check=True,
    env=hook_env,
)
hook_output = hook_result.stdout
assert "<rehydrate-trigger>" in hook_output
assert '<rehydrate-runtime version="0.4.3" />' in hook_output
assert "<skill>" in hook_output
assert "<name>rehydrate:rehydrate</name>" in hook_output
assert skill_text in hook_output
assert "final meaningful work segment" in hook_output
assert "Before the first retry or workaround" in hook_output
assert "progressive query ladder" in hook_output
assert "scripts/query_session.py" in hook_output
assert "fixed record count or time window" in hook_output
assert "complete skill body is embedded below and is already loaded" in hook_output
assert "Do not open or resolve a cached SKILL.md locator" in hook_output
assert "PostToolUse" not in hook_output
assert "post-tool-checkpoint" not in hook_output
assert payload in hook_output
assert str(PLUGIN.resolve()) not in hook_output
assert len(hook_output.encode("utf-8")) <= command_hook["additionalContextLimit"] * 4

fallback_env = os.environ.copy()
fallback_env["PLUGIN_ROOT"] = str(ROOT / "missing-plugin-root")
fallback_result = subprocess.run(
    ["sh", str(posix_hook)],
    input=payload,
    text=True,
    capture_output=True,
    check=True,
    env=fallback_env,
)
fallback_output = fallback_result.stdout
assert "<skill-load-fallback>" in fallback_output
assert "<skill>" not in fallback_output
assert "already loaded" not in fallback_output
for phrase in required_fallback_phrases:
    assert phrase.lower() in fallback_output.lower(), f"Fallback output missing: {phrase}"
assert payload in fallback_output

with tempfile.TemporaryDirectory() as temp_dir:
    whitespace_skill = Path(temp_dir) / "skills" / "rehydrate" / "SKILL.md"
    whitespace_skill.parent.mkdir(parents=True)
    whitespace_skill.write_text(" \t\n", encoding="utf-8")
    whitespace_env = os.environ.copy()
    whitespace_env["PLUGIN_ROOT"] = temp_dir
    whitespace_result = subprocess.run(
        ["sh", str(posix_hook)],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
        env=whitespace_env,
    )
    assert "<skill-load-fallback>" in whitespace_result.stdout
    assert "<skill>" not in whitespace_result.stdout
    assert "already loaded" not in whitespace_result.stdout
    assert "final meaningful pre-compaction work segment" in whitespace_result.stdout

readme = (ROOT / "README.md").read_text(encoding="utf-8")
readme_search = re.sub(r"\s+", " ", readme)
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
assert f"rehydrate-codex-plugin-{release_version}" in readme
assert f"## {release_version} -" in changelog
for phrase in (
    "Current release: `0.4.3`.",
    "final meaningful pre-compaction work segment",
    "latest genuine user message before the compaction boundary",
    "immediate tail does not replace whole-session recovery",
    "Progressive history queries",
    "scripts/query_session.py",
    "codex plugin list --json",
    "Why 0.4.3 uses SessionStart only",
    "Version `0.4.1` removes that hook and scan",
    "mandatory model-level skill contract",
    "Before the first retry or workaround",
    "most recent verified success",
    "Runtime skill name",
    "Plugin reload limitation",
    "rehydrate:rehydrate",
    "allow_implicit_invocation: false",
    "Enable the hook in Codex app",
    "approve `SessionStart` individually",
    "Start a new task before testing post-compaction activation",
    "Three compactions",
    "4,356 chars",
    "2,332 chars",
    "2,623 chars",
    "not a stable Codex API guarantee",
    "45,025",
    "5.2 MB",
    "73` entries",
    "Page sizes and preview lengths are output controls",
    "query_session.py\" <outline|slice|search|show>",
    "positional subcommands",
    "Values above a cap are capped",
    "80..2000",
    "next_cursor_before_line",
    "--cursor-before-line",
    "Remove the plugin before removing the marketplace",
    "codex plugin remove rehydrate@rehydrate-marketplace",
    "codex plugin marketplace remove rehydrate-marketplace",
):
    assert phrase in readme_search, f"README missing documented behavior: {phrase}"

for stale_phrase in (
    "approve its `SessionStart` and `PostToolUse`",
    "Confirm that both hooks",
    "rehydrate-after-tool",
    "post-tool-checkpoint=",
):
    assert stale_phrase not in readme, f"README contains stale active-hook wording: {stale_phrase}"

privacy = re.sub(r"\s+", " ", (ROOT / "PRIVACY.md").read_text(encoding="utf-8").lower())
security = re.sub(r"\s+", " ", (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower())
for text in (privacy, security):
    assert "final meaningful" in text
    assert "whole-session" in text
    assert "observable assistant" in text
    assert "hidden reasoning" in text
    assert "encrypted content" in text
    assert "before the first retry or workaround" in text
    assert "most recent verified success" in text
    assert "bounded" in text
    assert "turn_id" in text
    assert "call_id" in text
    assert "cell_id" in text
    assert "session_id" in text
    assert "history-query" in text
assert "no per-tool hook" in privacy
assert "model-level contract" in security
assert "posttooluse" not in privacy
assert "posttooluse" not in security

for path in PLUGIN.rglob("*"):
    if path.is_file() and path.suffix in {".json", ".md", ".ps1", ".py", ".sh", ".yaml"}:
        content = path.read_text(encoding="utf-8")
        assert "/Users/" not in content, f"Host-specific path in {path}"
        assert "PostToolUse" not in content, f"Removed hook remains in plugin package: {path}"
        assert "rehydrate-after-tool" not in content, f"Removed handler remains in plugin package: {path}"

print("Repository validation passed")
