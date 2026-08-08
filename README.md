# Rehydrate for Codex

[![Validate](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml/badge.svg)](https://github.com/totolstoy/rehydrate-codex-plugin/actions/workflows/validate.yml)

Current release: `0.4.3`.

Rehydrate helps Codex continue a task accurately after context compaction. It selectively traces
relevant history across the whole session, from the user's initial goal through later discussion,
corrections, and observable assistant work.

It combines a compact `SessionStart` activation hook with a reusable skill. `SessionStart` runs only
after context compaction and injects the complete bundled skill instructions without exposing their
installation path. The skill uses Codex's native compacted summary as a baseline, first checks the
final meaningful work segment before compaction, then recovers details the summary may have compressed:
commentary and progress updates, tool calls and results, commands, patches, tests, failures, rollbacks,
and incomplete work. Version `0.4.2` adds a bounded, read-only structural query helper so candidate
history is indexed before selected turns and action chains are expanded. During active execution, the
skill can independently recheck earlier evidence whenever that evidence could change the next action.
Before the first context compaction, it remains inactive unless the user explicitly invokes
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
command hooks disabled. Open Codex app settings, locate the hooks or plugin hook permissions, and
confirm that Rehydrate's `SessionStart` hook is enabled and approved. Enable it manually if needed.

If `SessionStart` remains disabled, the plugin is still installed and `$rehydrate:rehydrate` can be
invoked manually, but automatic activation after context compaction will not run. Start a new task
after changing the hook setting.

## Offline install

Download the ZIP attached to a GitHub release, extract it, and add the extracted directory as a
local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/rehydrate-codex-plugin-0.4.3
codex plugin add rehydrate@rehydrate-marketplace
```

On Windows, use the absolute extracted directory path in the first command.

## Activation behavior

- Before context compaction, ordinary messages do not automatically invoke Rehydrate.
- After context compaction, the `SessionStart(source=compact)` hook injects the complete bundled
  Rehydrate instructions into the new context. It does not depend on another user turn or expose
  the skill's installation path.
- Before reconstructing the whole task trajectory, Rehydrate checks the final meaningful
  pre-compaction work segment. It anchors that segment at the latest genuine user message before the
  compaction boundary and follows visible assistant commentary and observable calls and results to
  the boundary, excluding generated summaries, hook and environment wrappers, lifecycle telemetry,
  empty records, and nested `replacement_history`.
- Rehydrate starts with the native compacted summary, then follows the relevant chronology from the
  initial user goal through later revisions and multi-turn decisions. It is not limited to the last
  segment before compaction, and the immediate tail does not replace whole-session recovery.
- It prioritizes observable assistant execution details and distinguishes planned, attempted,
  executed, verified, failed, rolled-back, and incomplete work.
- It first builds a bounded structural index, selects exact `turn_id`, line, `call_id`, or async-handle
  anchors, and only then expands the evidence needed for the task.
- It does not wait for another user message to detect missing details. At material action boundaries,
  it can recheck an earlier command, path, patch, error, test result, correction, or completion state
  before choosing the next action.
- A material failure creates a mandatory recovery checkpoint. Before the first retry or workaround,
  Rehydrate runs one targeted lookup across the persisted earlier session for the same operation,
  tool, target, command, and stable error fragments, even if the summary suggests an obvious fix. It
  follows earlier failures to the most recent verified success and revalidates mutable prerequisites
  before reusing that fix.
- A lookup may be reused only when the same operation, target, and error-signature key has already
  been queried since activation. Expected, accepted negative probe branches with a predefined
  interpretation and next step do not trigger this checkpoint, and repeated failures with the same
  key do not cause repeated scans.
- An unexpected failure must return control to the model before a retry or workaround. The Agent is
  instructed not to pre-author automatic recovery inside the same code-mode script unless the
  negative branch is an expected probe with a predefined interpretation and next step.
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
a sidecar task-state file, or replace Codex's native compacted summary. Recovery history is filtered
and read selectively, while recovered conclusions stay in the current working context.

### Progressive history queries

Version `0.4.2` bundles `scripts/query_session.py`, a Python 3.10+ helper with no third-party packages.
The Agent resolves the current installed plugin source through `codex plugin list --json`, rather
than trusting a cache path retained by an older task. If the helper or Python is unavailable, the
skill requires the same staged protocol with a structured JSON parser.

The query stages are:

1. `outline` lists genuine user-message anchors and top-level compaction boundaries.
2. `slice` pages through safe records for one selected user turn or exclusive line span.
3. `search` finds bounded action-chain candidates using literal term intersections.
4. `show` expands selected records together with their call/result and async continuation chain.

Version `0.4.3` fixes the query invocation as one immutable launcher plus one positional subcommand:

```text
python3 "<resolved-source.path>/scripts/query_session.py" <outline|slice|search|show> ...
```

The Agent constructs that helper path once from the single installed, enabled Rehydrate entry and
keeps it unchanged for every query. `outline`, `slice`, `search`, and `show` are positional
subcommands of `query_session.py`, not separate `outline_session.py`, `slice_session.py`,
`search_session.py`, or `show_session.py` files.

The CLI help exposes each output control's default, minimum, and cap from the same definitions used
by the parser:

| Command | `--limit` default / range | `--preview-chars` default / range |
|---|---:|---:|
| `outline` | 24 / 1..64 | 120 / 40..320 |
| `slice` | 24 / 1..32 | 240 / 40..500 |
| `search` | 4 / 1..12 | 160 / 40..400 |
| `show` | 8 / 1..12 | 1000 / 80..2000 |

Values above a cap are capped instead of failing the recovery query. Values below a minimum and
non-integers remain invalid. The Agent still starts with defaults and narrows by semantic anchors;
automatic capping does not relax the 16,000-byte response ceiling.

`turn_id` associates a user's request with its assistant work, `call_id` pairs immediate calls and
results, and an opaque `cell_id` plus numeric `session_id` follows a yielded command through waits or
writes to terminal status, including an explicit continuation in a later user turn or after a
compaction. A completed chain is never joined to a later reuse of the same handle. A running result is
not treated as completion, and an absent mate is marked unpaired. Terminal state comes from the outer
response status, a top-level structured result, or a recognized execution envelope; nested log
fragments cannot override it. History-query calls, direct transcript readers, and their echoed output
are excluded from ordinary action search. Merely searching documentation for helper syntax is not a
history query. An explicit query-mechanism diagnostic exposes only structural identifiers and terminal
status, never the echoed query body or handles found inside it.

Page sizes and preview lengths are output controls, not limits on how far back Rehydrate can reason.
Flags such as `has_more`, `needs_refinement`, `input_incomplete`, `output_limited`, and
`excerpt_truncated` require another page or a narrower anchor when they affect the conclusion. The
Agent starts each stage with the helper defaults and must narrow by compaction window, turn, operation,
target, call, handle, and error intersection; it must not explore with maximum page or preview values
or fix truncation by requesting a larger broad dump. A larger local excerpt is appropriate only after
one exact record has been selected and its default excerpt is insufficient. Each response is capped
at 16,000 encoded bytes; when byte trimming removes page units, the helper still returns an exclusive
continuation cursor so omitted candidates remain reachable.

For `search`, `--before-line` and `--after-line` are fixed semantic evidence bounds. Action-chain
pagination is separate: repeat those bounds and pass `next_cursor_before_line` back as
`--cursor-before-line`. This prevents evidence after a compaction boundary from changing the reported
state before that boundary, while keeping interleaved async chains atomic across pages.

This design follows a real `0.4.1` failure observed `2026-08-04` under Codex app `26.727.51351`, build
`6119`, embedded CLI `0.146.0-alpha.9.2`. One ad hoc range-plus-keyword query produced `45,025` tokens
across `275` lines and was truncated; flattening safe-looking tool outputs could produce about
`5.2 MB`. On the same
roughly 11,000-record session, the complete user-message and compaction outline was only `73` entries
and about `8.7 KB` before pagination. The helper keeps candidate output bounded and expands only the
selected evidence.

### Why 0.4.3 uses SessionStart only

The complete compact-injected skill remains in the active model context until the next compaction.
At that boundary, Codex replaces the context and `SessionStart(source=compact)` injects the current
skill again. A per-tool hook is therefore not needed to keep Rehydrate active. The compact hook also
emits `<rehydrate-runtime version="0.4.3" />` solely as a diagnostic identifier for the injected
version; no runtime handler consumes it.

The unreleased `0.4.0` local experiment added a Bash `PostToolUse` reminder. Unified exec supplied
raw command output without a structured exit code, so the handler could not selectively identify a
failure and instead had to inject the same reminder after successful and failed Bash results. It did
not add recovery capability beyond the already active skill, did not cover every MCP or hosted-tool
failure, and could not interrupt a retry pre-authored inside the same code-mode script. Its
full-transcript activation scan also measured about `204ms` per Bash result on a 19 MB session.
Version `0.4.1` removes that hook and scan.

The material-failure checkpoint remains a mandatory model-level skill contract. Before the first
retry or workaround, the Agent must search matching earlier session evidence and revalidate mutable
prerequisites. The skill also forbids pre-authoring an unexpected same-script retry so that a failure
can return control to the model and the checkpoint can run.

## Observed plugin loading behavior

The following findings were verified with Codex desktop app `26.727.51351` (released
`2026-08-01`), embedded `codex-cli 0.146.0-alpha.9.2`, on macOS arm64. They describe observed
behavior as of `2026-08-03`, not a stable plugin API guarantee.

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

The same stale task snapshot can surface as a cached-version path error. During local `0.3.2`
testing, a long-lived task successfully received the current compact trigger but then tried to reopen
a `0.3.1` skill locator retained from earlier task context. The current `0.3.2` cache existed,
`codex plugin list` still reported the plugin as installed and enabled, and the current cached skill
matched the source. In this state, the error does not indicate transcript loss or plugin-content
corruption. Fully restart Codex app and start a new task so it receives the current cache paths. Do
not recreate the old cache directory manually.
Starting with `0.4.1`, compact activation also marks its embedded skill body as already loaded and
directs the agent not to reopen a cached `SKILL.md` locator retained by an older task snapshot.

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

Version `0.4.1` additionally checks the final meaningful pre-compaction work segment before the
whole-session pass. This is a logical turn segment, not the last raw JSONL record: it begins at the
latest genuine user message before the compaction boundary and includes the visible commentary and
paired observable actions that followed. The check recovers immediate state without allowing the
tail to replace the initial goal, later corrections, or other relevant history.

Version `0.4.2` keeps that semantic scope but changes how evidence enters working context. It pages a
safe structural outline, expands selected turns and action chains, and reports incomplete or
truncated projections explicitly. The page size is never used as a claim that older history is
irrelevant.

## Update

```bash
codex plugin marketplace upgrade rehydrate-marketplace
codex plugin add rehydrate@rehydrate-marketplace
```

After every update:

1. Fully quit and restart Codex app. Do not rely on the plugin page showing the new version number.
2. Open the Rehydrate plugin page. Updated hooks may be shown as modified or untrusted; click
   **Trust all** (**全部信任**) or approve `SessionStart` individually.
3. Confirm that the hook is enabled and trusted.
4. Start a new task before testing post-compaction activation.

Version `0.4.3` does not change `hooks.json`; an already trusted `SessionStart` declaration may reuse
its existing trust without showing a new prompt. The App restart and new task are still required for
reliable plugin and skill cache pickup.

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
- The `SessionStart` activation hook runs only after Codex context compaction.
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
- The query helper uses Python 3.10 or newer when available and has no third-party dependencies. If a
  compatible Python is not available, the embedded skill requires the same staged protocol through a
  structured parser.
- Codex must include plugin and hook support.

The repository validates both platform implementations of the compact hook in GitHub Actions.

## Development

Repository layout:

```text
.agents/plugins/marketplace.json
plugins/rehydrate/
tests/validate.py
tests/test_query_session.py
```

Run the repository checks with Python and PyYAML installed:

```bash
python3 tests/validate.py
python3 tests/test_query_session.py
sh -n plugins/rehydrate/scripts/rehydrate-on-compact.sh
```

## License

[MIT](LICENSE)
