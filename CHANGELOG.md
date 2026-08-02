# Changelog

All notable changes to this project are documented in this file.

## 0.3.1 - 2026-08-02

- Correct the plugin-qualified runtime skill name to `$rehydrate:rehydrate` while keeping the
  source frontmatter name `rehydrate`.
- Replace the ineffective hook-emitted invocation token with direct injection of the complete
  bundled skill instructions, without exposing the installation path.
- Keep a minimal recovery policy as a fallback if the bundled skill cannot be loaded.
- Document the current-task plugin hot-reload limitation and the distinction between plugin
  registration names and source skill names, verified with Codex app `26.727.51351` and embedded
  `codex-cli 0.146.0-alpha.9.2`.
- Change the compact hook status message so the normalized hook identity receives a new trust hash.
- Verify that an external CLI update can refresh the displayed manifest version while leaving the
  hook review state stale, even after the plugin page issues fresh `plugin/read` and `hooks/list`
  requests.
- Document that this App protocol has no hook or plugin change notification, external CLI installs
  cannot invalidate the running App cache, and hook invocation is unrelated to review discovery.
- Confirm that fully restarting Codex app surfaces the pending hook review, and require restart,
  explicit hook trust, and a new task after every plugin update.
- Document the complete uninstall sequence for the public Git marketplace, including removal of the
  installed plugin before its marketplace and a full Codex app restart afterward.

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
