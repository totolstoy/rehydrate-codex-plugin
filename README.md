# Rehydrate for Codex

[![Validate](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml/badge.svg)](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml)

Rehydrate helps Codex continue a task accurately after context compaction. It selectively traces
relevant history across the whole session, from the user's initial goal through later discussion,
corrections, and observable assistant work.

It combines a compact `SessionStart` hook with a reusable skill. The hook runs only after context
compaction and injects the complete bundled skill instructions without exposing their installation
path. The skill uses Codex's native compacted summary as a baseline, then recovers details the
summary may have compressed: commentary and progress updates, tool calls and results, commands,
patches, tests, failures, rollbacks, and incomplete work. During active execution, it can
independently recheck earlier evidence whenever that evidence could change the next action. Before
the first context compaction, the skill remains inactive unless the user explicitly invokes
`$rehydrate:rehydrate`.

## Install

Add the public Git marketplace and install the plugin:

```bash
codex plugin marketplace add totolstoy/rehydrate-codex-plugin
codex plugin add rehydrate@rehydrate-marketplace
```

After installation:

1. Fully quit and restart Codex app.
2. Open the Rehydrate plugin page and click **Trust all** (shown as **全部信任** in the Chinese UI),
   or approve its `SessionStart` command hook individually.
3. Confirm that the hook is enabled and trusted.
4. Start a new task so Codex loads the new skill and hook.

### Enable the hook in Codex app

Depending on the Codex app build and existing permissions, installing the plugin may leave its
command hook disabled. Open Codex app settings, locate the hooks or plugin hook permissions, and
confirm that Rehydrate's `SessionStart` hook is enabled and approved. Enable it manually if needed.

If the hook remains disabled, the plugin is still installed and `$rehydrate:rehydrate` can be
invoked manually, but automatic activation after context compaction will not run. Start a new task
after changing the hook setting.

## Offline install

Download the ZIP attached to a GitHub release, extract it, and add the extracted directory as a
local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/rehydrate-codex-plugin-0.3.1
codex plugin add rehydrate@rehydrate-marketplace
```

On Windows, use the absolute extracted directory path in the first command.

## Activation behavior

- Before context compaction, ordinary messages do not automatically invoke Rehydrate.
- After context compaction, the `SessionStart(source=compact)` hook injects the complete bundled
  Rehydrate instructions into the new context. It does not depend on another user turn or expose
  the skill's installation path.
- Rehydrate starts with the native compacted summary, then follows the relevant chronology from the
  initial user goal through later revisions and multi-turn decisions. It is not limited to the last
  segment before compaction.
- It prioritizes observable assistant execution details and distinguishes planned, attempted,
  executed, verified, failed, rolled-back, and incomplete work.
- It does not wait for another user message to detect missing details. At material action boundaries,
  it can recheck an earlier command, path, patch, error, test result, correction, or completion state
  before choosing the next action.
- Later requests are interpreted against that session-wide chronology. Additional transcript reads
  remain targeted and occur only when they can materially improve understanding or prevent repeated
  work.
- Users can still invoke `$rehydrate:rehydrate` manually at any time.

Referential follow-up requests such as "continue", "use the earlier constraints", or "fix what we
just discussed" are interpreted using the recovered chronology and all newer turns.

You can also invoke the skill directly:

```text
Use $rehydrate:rehydrate to recover relevant session history and recheck prior evidence during execution.
```

Rehydrate does not load the complete session transcript by default, copy it into the prompt, create
a sidecar task-state file, or replace Codex's native compacted summary. Transcript history is
filtered and read selectively, while recovered conclusions stay in the current working context.
It does not continuously monitor or rescan the transcript when the next action is already clear.

## Observed plugin loading behavior

The following findings were verified with Codex desktop app `26.727.51351` (released
`2026-08-01`), embedded `codex-cli 0.146.0-alpha.9.2`, on macOS arm64. They describe observed
behavior as of `2026-08-02`, not a stable plugin API guarantee.

### Runtime skill name

The skill's source frontmatter remains `name: rehydrate`, while plugin namespacing registers it at
runtime as `rehydrate:rehydrate`. The correct manual invocation is therefore
`$rehydrate:rehydrate`, not `$rehydrate`.

This plugin intentionally keeps `allow_implicit_invocation: false`, so the skill may be absent from
the model's default `Available skills` list even when `skills/list` reports it as installed and
enabled. A user-originated explicit invocation can still inject the complete `<skill>` block.

A hook-emitted `$rehydrate:rehydrate` token is different: the compact `SessionStart` output is added
as developer context after that turn's explicit skill selection. The token alone does not expand
`SKILL.md`. The local `0.3.0` test build therefore had the hook load and inject the bundled
instructions directly; the qualified runtime name remains the public manual entry point.

### Plugin reload limitation

Reinstalling or upgrading a plugin refreshed the global plugin catalog, `skills/list`, and
`hooks/list`, but did not reliably rebuild the hook snapshot already held by an open task.
Consequently, an enabled and trusted result from `hooks/list` confirms installation health but does
not prove that a previously opened task loaded that hook.

After an external CLI reinstall or hook change, restart Codex app for reliable plugin-cache pickup,
approve the new hook hash, and then start a new task. When an App-internal update has already
invalidated the plugin cache, starting a new task is sufficient. An already open task sees hook-state
changes only after its runtime configuration is reloaded. This limitation also explains why
uninstalling and reinstalling during a task can leave later compactions without the newly installed
hook.

In this build, the App Server protocol emits `skills/changed` but no corresponding `hooks/changed`
or `plugins/changed` notification, and the external CLI install path cannot invoke the running App's
cache-invalidation callback. In a live `0.3.1` test, reopening the plugin page issued both
`plugin/read` and `hooks/list`: the page updated its manifest version from `0.3.0` to `0.3.1`, but it
did not show the new hook review because `hooks/list` reused cached plugin hook sources. Reopening the
page alone was therefore insufficient.

After fully quitting and restarting Codex app, the same `0.3.1` installation displayed the expected
hook review request. This confirms that an App restart clears the stale plugin-hook cache. Seeing the
new version number alone does not prove that the updated hook was loaded or trusted.

An App-side plugin install, a configuration mutation, or an App restart clears the relevant cache;
hook execution does not. A skill invocation or compaction may coincide with a later refresh, but
neither is required for discovering review state and neither guarantees cache invalidation.

Hook trust tracks the normalized hook declaration rather than the plugin version or bundled script
contents. A version-only or script-only update may keep the previous hook trusted. Version `0.3.1`
changes the compact hook's status message to produce a new trust hash for this refresh test without
changing its recovery behavior.

## Observed Codex compaction behavior

The following is an empirical snapshot, not a stable Codex API guarantee:

- Codex desktop app: `26.727.51351` (released `2026-08-01`), build `6119`
- Embedded CLI: `codex-cli 0.146.0-alpha.9.2`
- Platform: macOS arm64
- Observed: `2026-08-02`

Three compactions in one real session produced:

| Compaction | Native summary | `replacement_history` | User-role entries | Developer-role entries | Retained text |
|---|---:|---:|---:|---:|---:|
| 1 | 4,356 chars | 11 | 8 | 3 | 21,043 chars |
| 2 | 2,332 chars | 15 | 12 | 3 | 19,727 chars |
| 3 | 2,623 chars | 32 | 29 | 3 | 20,389 chars |

In this sample, the substantive user prompts from before each compaction were retained essentially
verbatim. One user-role entry was the synthesized compacted summary, and the runtime environment
wrapper was refreshed. No assistant message, tool or function call/result, or reasoning record was
retained verbatim in `replacement_history`; observable assistant work was represented only through
the lossy native summary.

There was no fixed "keep the latest N messages" count. This is why Rehydrate searches the relevant
chronology across the whole session and gives extra attention to observable assistant action records:
the native context preserved the user's discussion well in this sample, while exact commands,
patches, test evidence, failures, and intermediate progress were the details most likely to be lost.
Internal transcript fields and selection behavior may change in later Codex versions.

## Update

```bash
codex plugin marketplace upgrade rehydrate-marketplace
codex plugin add rehydrate@rehydrate-marketplace
```

After every update:

1. Fully quit and restart Codex app. Do not rely on the plugin page showing the new version number.
2. Open the Rehydrate plugin page. The updated hook may be shown as modified or untrusted; click
   **Trust all** (**全部信任**) or approve the updated `SessionStart` hook individually.
3. Confirm that the hook is enabled and trusted.
4. Start a new task before testing post-compaction activation.

## Uninstall

Remove the plugin before removing the marketplace that supplied it:

```bash
codex plugin remove rehydrate@rehydrate-marketplace
codex plugin marketplace remove rehydrate-marketplace
```

If the plugin has already been removed, run only the second command. These commands delete the
local plugin installation and Codex's configured marketplace snapshot; they do not delete or alter
the GitHub repository. Fully quit and restart Codex app after uninstalling so the running app drops
any cached plugin, skill, and hook state.

## Privacy and security

- The bundled hook scripts do not make network requests.
- The automatic hook runs only after Codex context compaction.
- The hook passes Codex the `SessionStart` metadata already provided by Codex.
- The skill may direct Codex to read selected user messages, visible assistant messages, and
  observable tool or command records from the current local session transcript.
- Hidden reasoning, reasoning summaries, encrypted content, credentials, and unrelated sensitive
  data are excluded from recovery.
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
