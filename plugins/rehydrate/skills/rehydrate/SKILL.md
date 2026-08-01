---
name: rehydrate
description: Restore continuity after Codex context compaction. Use only when a compact SessionStart hook explicitly invokes $rehydrate or when the user explicitly invokes $rehydrate. Do not invoke automatically for ordinary follow-up requests before context compaction. Once active, preserve the latest user intent across turns and selectively consult the current session transcript without loading it in full by default.
---

# Rehydrate

Run only after explicit invocation. The normal automatic path is the `SessionStart(source=compact)`
hook. Before context compaction, remain inactive unless the user explicitly invokes `$rehydrate`.

Maintain an active task state containing the current goal, user intent, constraints, decisions,
completed work and evidence, failures or rollbacks, pending work, and unresolved questions. Keep it
in working context; do not create a sidecar state file unless the user requests one.

For every subsequent user message:

1. Interpret it against the active task state. Treat a short or referential follow-up as a delta to
   the existing task, preserving prior constraints unless the user explicitly supersedes them.
2. If the request is self-contained and the active state is sufficient, continue without reading
   the transcript. If it refers to missing history, conflicts with the state, or could materially
   change the action, selectively inspect the transcript before acting.
3. Prefer an exact `transcript_path` supplied by `SessionStart(source=compact)`. Otherwise read the
   session ID from `CODEX_THREAD_ID`. Resolve the Codex home from `CODEX_HOME` when set, then
   `$HOME/.codex` on POSIX or the user's `.codex` directory on Windows. Locate the exact
   `*-<session-id>.jsonl` under `sessions` or `archived_sessions`; never choose by modification time.
4. Use available structured JSON tools and targeted search commands such as `rg`, `jq`, `sed`, or
   PowerShell equivalents to recover only the relevant user requirements, decisions, completed
   results, failures, and pending work. Do not traverse `replacement_history` as new events, expose
   reasoning or encrypted content, or read tool output unless it is needed as evidence.
5. Reconcile recovered history with current state. Current instructions and the newest user request
   take precedence over historical requests; current workspace evidence takes precedence over old
   progress claims; aborted or rolled-back work is not complete. Treat an old assistant proposal as
   a decision only when the user accepted it or current evidence confirms it.
6. Update the active task state after each user message and material result. Resume the work without
   a separate recovery report unless a conflict, ambiguity, or blocker requires the user's input.

When the user clearly starts an unrelated task, reset the active task state instead of carrying old
constraints into the new task.
