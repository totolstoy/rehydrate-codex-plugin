# Changelog

All notable changes to this project are documented in this file.

## 0.2.1 - 2026-08-02

- Use Codex's native compacted summary as a baseline without creating a sidecar task-state file.
- Recover the relevant chronology across the whole session, including the user's initial goal,
  later discussion, corrections, accepted decisions, and scope changes.
- Prioritize observable assistant actions such as commentary, tool calls and results, commands,
  patches, tests, failures, rollbacks, and incomplete work.
- Distinguish planned, attempted, executed, and verified work, and exclude hidden reasoning,
  reasoning summaries, encrypted content, credentials, and unrelated sensitive data.
- Allow autonomous targeted lookups during execution whenever prior evidence could change the next
  command, target, retry, rollback, consequential external action, or completion judgment.
- Document version-specific observations from three real Codex context compactions.
- Document that the Codex app may require users to enable the plugin hook manually.

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
