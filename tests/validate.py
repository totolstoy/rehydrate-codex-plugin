#!/usr/bin/env python3

import json
import re
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
assert manifest["version"] == "0.2.0"
assert manifest["license"] == "MIT"
assert manifest["skills"] == "./skills/"
assert manifest["repository"].startswith("https://github.com/")

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
assert "context compaction" in skill_meta["description"].lower()
assert "do not invoke automatically" in skill_meta["description"].lower()
assert "replacement_history" in skill_text

agent_meta = yaml.safe_load(
    (PLUGIN / "skills" / "rehydrate" / "agents" / "openai.yaml").read_text(encoding="utf-8")
)
assert "$rehydrate" in agent_meta["interface"]["default_prompt"]
assert agent_meta["policy"]["allow_implicit_invocation"] is False

hooks = load_json(PLUGIN / "hooks" / "hooks.json")
session_hooks = hooks["hooks"]["SessionStart"]
assert len(session_hooks) == 1
assert session_hooks[0]["matcher"] == "^compact$"
command_hook = session_hooks[0]["hooks"][0]
assert command_hook["type"] == "command"
assert "${PLUGIN_ROOT}" in command_hook["command"]
assert "%PLUGIN_ROOT%" in command_hook["commandWindows"]
assert command_hook["additionalContextLimit"] == 2000

for script in ("rehydrate-on-compact.sh", "rehydrate-on-compact.ps1"):
    script_path = PLUGIN / "scripts" / script
    assert script_path.is_file()
    script_text = script_path.read_text(encoding="utf-8")
    assert "$rehydrate" in script_text
    assert "perform the recovery directly" in script_text

for path in PLUGIN.rglob("*"):
    if path.is_file() and path.suffix in {".json", ".md", ".ps1", ".sh", ".yaml"}:
        content = path.read_text(encoding="utf-8")
        assert "/Users/" not in content, f"Host-specific path in {path}"

print("Repository validation passed")
