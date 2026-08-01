# Rehydrate for Codex

[![Validate](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml/badge.svg)](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml)

Rehydrate keeps Codex grounded in the active task after context compaction and during subsequent
follow-up requests that depend on earlier turns.

It combines a compact `SessionStart` hook with a reusable skill. The hook runs only after context
compaction and asks Codex to rebuild its active task state. The skill then interprets each new user
message against that state and reads only relevant transcript history when the current context is
insufficient. Before the first context compaction, the skill remains inactive unless the user
explicitly invokes `$rehydrate`.

## Install

Add the public Git marketplace and install the plugin:

```bash
codex plugin marketplace add totolstoy/rehydrate-codex-plugin
codex plugin add rehydrate@rehydrate-marketplace
```

Review and approve the `SessionStart` command hook when Codex asks. Start a new task after
installation so Codex loads the new skill and hook.

## Offline install

Download the ZIP attached to a GitHub release, extract it, and add the extracted directory as a
local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/rehydrate-codex-plugin-0.2.0
codex plugin add rehydrate@rehydrate-marketplace
```

On Windows, use the absolute extracted directory path in the first command.

## Activation behavior

- Before context compaction, ordinary messages do not automatically invoke Rehydrate.
- After context compaction, the `SessionStart(source=compact)` hook injects an explicit `$rehydrate`
  request plus a direct recovery fallback.
- Once active, Rehydrate maintains the recovered task state across subsequent messages.
- Users can still invoke `$rehydrate` manually at any time.

Referential follow-up requests such as "continue", "use the earlier constraints", or "fix what we
just discussed" use the recovered state only after Rehydrate has been activated.

You can also invoke the skill directly:

```text
Use $rehydrate to recover the active task state for this session.
```

Rehydrate does not load the complete session transcript by default. It maintains a compact active
task state and selectively consults persisted history only when needed to resolve missing or
conflicting context.

## Update

```bash
codex plugin marketplace upgrade rehydrate-marketplace
codex plugin add rehydrate@rehydrate-marketplace
```

Start a new task after upgrading.

## Uninstall

```bash
codex plugin remove rehydrate@rehydrate-marketplace
codex plugin marketplace remove rehydrate-marketplace
```

## Privacy and security

- The bundled hook scripts do not make network requests.
- The automatic hook runs only after Codex context compaction.
- The hook passes Codex the `SessionStart` metadata already provided by Codex.
- When necessary, the skill may direct Codex to read selected entries from the current local
  session transcript.
- Transcript content is treated as historical evidence, not as current instructions.
- The plugin does not create a separate history database or upload transcript content.
- Command hook execution requires user approval and remains subject to Codex permissions and
  workspace policy.

See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md) for details.

## Platform support

- macOS and Linux use the POSIX `sh` hook.
- Windows uses the PowerShell hook.
- Codex must include plugin and hook support.

The repository validates both hook implementations in GitHub Actions.

## Development

Repository layout:

```text
.agents/plugins/marketplace.json
plugins/rehydrate/
tests/validate.py
```

Run the repository checks with Python and PyYAML installed:

```bash
python3 tests/validate.py
sh -n plugins/rehydrate/scripts/rehydrate-on-compact.sh
```

## License

[MIT](LICENSE)
