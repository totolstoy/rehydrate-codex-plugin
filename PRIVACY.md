# Privacy

Rehydrate is a local Codex plugin. Its bundled hook scripts do not send network requests, operate a
remote service, or collect analytics.

The automatic hook runs only after Codex context compaction. Before compaction, the skill remains
inactive unless the user explicitly invokes `$rehydrate`.

## Data used

After Codex compacts a task, the hook receives the `SessionStart` metadata supplied by Codex and
returns a short activation instruction. The skill may then read selected records across the current
task's locally persisted transcript: user messages, visible assistant messages and commentary,
tool or function calls and their results, commands, patches, file changes, tests, failures,
rollbacks, and incomplete work.

These targeted reads may occur during initial recovery, while handling a later user request, or
during active execution when prior evidence could materially change the next action. Rehydrate does
not continuously monitor the transcript.

Rehydrate excludes hidden reasoning, reasoning summaries, encrypted content, credentials, and
unrelated sensitive data. It uses structured field selection before text search so excluded record
types are not intentionally loaded into working context.

## Purpose

This information is used only to recover the relevant task chronology, preserve changes to the
user's goal across multiple turns, verify observable assistant actions, and prevent later requests
from being misunderstood or prior work from being repeated, contradicted, or incorrectly reported
as complete.

## Storage and transmission

Rehydrate does not create a separate transcript database or upload transcript contents. The plugin
does not retain an additional copy of recovered history or create a sidecar task-state file.
Recovered conclusions remain only in Codex's current working context. Existing Codex storage,
retention, permissions, and product policies still apply to the underlying task transcript.

## User control

Users approve the command hook during installation. Removing the plugin disables its hook and skill:

```bash
codex plugin remove rehydrate@rehydrate-marketplace
```

Privacy questions can be opened as an issue in this repository without including private transcript
content.
