# Changelog

All notable changes to this project are documented in this file.

## 0.2.0 - 2026-08-02

- Disable implicit skill invocation before context compaction.
- Explicitly invoke `$rehydrate` from the compact-only `SessionStart` hook.
- Document and test the post-compaction-only automatic activation boundary.

## 0.1.0 - 2026-08-02

- Add context recovery after Codex context compaction.
- Maintain an active task state across referential follow-up requests.
- Selectively consult the exact current session transcript when context is missing.
- Support POSIX shell and Windows PowerShell `SessionStart` hooks.
- Add public Git marketplace and offline ZIP distribution.
