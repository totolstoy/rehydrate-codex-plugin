# Privacy

Rehydrate is a local Codex plugin. Its bundled hook scripts do not send network requests, operate a
remote service, or collect analytics.

The `SessionStart` activation hook runs only after Codex context compaction. The skill remains
inactive before compaction unless the user explicitly invokes `$rehydrate:rehydrate`. The compact
hook injects the complete skill after each compaction so its policy remains available throughout the
new context window.

Version `0.4.2` includes a local, read-only Python 3.10+ helper for progressive transcript queries. The
helper makes no network requests, writes no files, creates no index database, and uses no third-party
Python packages. The skill locates the current helper through Codex's structured installed-plugin
listing instead of using a cached path from an older task.

## Data used

After Codex compacts a task, the activation hook receives the `SessionStart` metadata supplied by Codex and
injects the bundled skill instructions into the new context. It does not expose the installation
path in that context. The skill may then read selected records across the current task's locally
persisted transcript: user messages, visible assistant messages and commentary, tool or function
calls and their results, commands, patches, file changes, tests, failures, rollbacks, and incomplete
work.

Initial recovery first selects the final meaningful work segment before the latest compaction. It
uses the latest genuine user request or correction as an anchor and includes only the visible
assistant messages and observable actions needed to recover the immediate intent, latest verified
state, unresolved work, and next step. Synthesized compact summaries, hook, skill, and environment
wrappers, lifecycle telemetry, empty records, hidden record types, and nested `replacement_history`
are excluded from that segment. This tail check supplements the relevant whole-session chronology;
it does not replace it.

These targeted reads may occur during initial recovery, while handling a later user request, or
during active execution when prior evidence could materially change the next action. Rehydrate does
not continuously read recovery history.

The helper first returns a bounded structural outline or candidate index. It expands only selected
user turns, records, call/result pairs, and observable async continuations. Page sizes and preview
lengths constrain one response but do not limit the historical search: incomplete results are paged
or narrowed by semantic anchors rather than converted into a larger transcript dump. Byte-limited
pages retain an exclusive continuation cursor. Prior history-query calls and their echoed output are
excluded from ordinary evidence search, as are direct commands that read the session JSONL; an
explicit query-mechanism diagnostic retains only structural identifiers and status, not the echoed
query body or handles found inside it. Search line bounds remain fixed evidence scope while a separate
cursor advances through atomic action-chain candidates.

The structural projection may retain `turn_id` to associate a genuine user turn, `call_id` to pair an
immediate call and result, and an observable opaque `cell_id` or numeric `session_id` value to follow
a yielded command to terminal status, including an explicit continuation after a later user turn or
compaction. Completed chains are not joined to later handle reuse. These identifiers remain inside
the current local Codex task context.

Version `0.4.2` has no per-tool hook and does not rescan the transcript after every command. Recovery
reads occur only under the active skill policy when initial continuity, a later request, a material
action boundary, or a material failure makes earlier evidence relevant.

After a material command or tool failure, a targeted read compares the current operation, target,
command, and stable error fragments with earlier failures and verified recoveries. This happens
before the first retry or workaround, and matching failures are followed through to the most recent
verified success. A lookup may be reused only for the same key after it has been performed since
activation. A deliberate probe is exempt only when its negative result is an expected, accepted
branch with a predefined interpretation and next step. Repeated failures with the same key do not
cause repeated scans.

Rehydrate excludes hidden reasoning, reasoning summaries, encrypted content, developer and runtime
wrappers, nested `replacement_history`, common credential forms, and unrelated sensitive data. The
helper allowlists visible message blocks and selected observable action fields before matching, so
excluded record types are not intentionally loaded into working context.

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
