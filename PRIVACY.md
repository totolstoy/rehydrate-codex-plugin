# Privacy

Rehydrate is a local Codex plugin. Its bundled hook scripts do not send network requests, operate a
remote service, or collect analytics.

The automatic hook runs only after Codex context compaction. Before compaction, the skill remains
inactive unless the user explicitly invokes `$rehydrate`.

## Data used

After Codex compacts a task, the hook receives the `SessionStart` metadata supplied by Codex and
returns a short recovery instruction. When the active context is insufficient, the skill may direct
Codex to read selected entries from the current task's locally persisted transcript.

## Purpose

This information is used only to reconstruct the active task state, preserve the latest user intent,
and interpret later requests against relevant earlier context.

## Storage and transmission

Rehydrate does not create a separate transcript database or upload transcript contents. The plugin
does not retain an additional copy of recovered history. Existing Codex storage, retention,
permissions, and product policies still apply to the underlying task transcript.

## User control

Users approve the command hook during installation. Removing the plugin disables its hook and skill:

```bash
codex plugin remove rehydrate@rehydrate-marketplace
```

Privacy questions can be opened as an issue in this repository without including private transcript
content.
