# Changelog

All notable changes to this project are documented in this file.

## 0.4.3 - 2026-08-08

- Fix the Agent-facing query contract to use one immutable `scripts/query_session.py` launcher with
  `outline`, `slice`, `search`, or `show` as positional subcommands, and explicitly forbid probing
  derived `*_session.py` filenames.
- Define `--limit` and `--preview-chars` defaults, minimums, and caps once, then expose the same
  values in top-level and subcommand help so callers no longer need to guess numeric contracts.
- Cap above-maximum output controls instead of rejecting the recovery query, while continuing to
  reject below-minimum and non-integer values and retaining the 16,000-byte response ceiling.
- Add regression coverage for the single launcher, discoverable contracts, high-value capping, and
  unchanged fail-closed lower/type validation on both the full skill and hook fallback paths.

## 0.4.2 - 2026-08-04

- Add a dependency-free, read-only `query_session.py` helper that produces bounded JSON projections
  instead of relying on ad hoc whole-transcript `jq` and `rg` output.
- Recover history progressively through `outline`, `slice`, `search`, and `show`: index candidates,
  select exact anchors, expand related evidence, and refine only when the current evidence is
  incomplete.
- Correlate genuine user turns with `turn_id`, immediate tool pairs with `call_id`, and yielded
  commands with opaque `cell_id` and numeric `session_id` handles across later turns and explicit
  cross-compaction continuations through terminal status, without joining completed handle reuse.
- Deduplicate structurally mirrored visible messages in a linear pass only inside the same compaction
  window, preserve distinct repeated messages, and require an uninterrupted structural relationship
  before treating a fallback compaction event as a boundary mirror.
- Keep `show` selectors stable across continuation pages, exclude compact wrappers and history-query
  echoes, distinguish fixed search bounds from `--cursor-before-line` pagination, and derive terminal
  state only from outer response status, top-level structured results, or recognized execution
  envelopes rather than nested log fragments.
- Bound every helper response to 16,000 encoded bytes, center excerpts on literal intersections,
  preserve continuation cursors after count or byte trimming, expose incomplete-state flags, and
  require narrower anchors instead of larger broad output after truncation.
- Fail closed on hidden or unknown content blocks and filter reasoning, encrypted blocks, developer
  wrappers, nested `replacement_history`, structured secrets, headers, and CLI credential options
  before matching or output. Query-mechanism diagnostics retain only structure and status, never an
  echoed query body.
- Isolate direct POSIX and PowerShell transcript readers as query mechanisms while keeping ordinary
  project JSONL searches and source/documentation searches available as evidence.
- Resolve the current helper source through `codex plugin list --json` rather than a stale cached skill
  locator, with the existing structured-parser workflow as a fallback when Python is unavailable.
- Keep `hooks.json` unchanged, so this local update does not create a new hook trust identity.

## 0.4.1 - 2026-08-03

- Add a mandatory recovery checkpoint after a material command or tool failure, before the first
  retry or workaround.
- Match earlier evidence by operation, tool, target, command, and stable error fragments, then follow
  prior failures through to the most recent verified success.
- Require the persisted-session lookup even when the summary suggests an obvious fix, while caching
  conclusions by operation, target, and error signature to avoid repeated scans.
- Revalidate mutable prerequisites before reusing an earlier fix, and exclude only expected,
  accepted negative probe branches whose interpretation and next step are predefined.
- Mark the complete compact-injected skill body as already loaded so an agent does not reopen a
  stale cached `SKILL.md` locator after an update, and document that this error does not imply
  transcript loss or plugin-content corruption.
- Before the whole-session pass, inspect the final meaningful pre-compaction work segment from the
  latest genuine user request or correction through visible assistant work at the compact boundary.
- Exclude synthesized summaries, hook and environment wrappers, lifecycle telemetry, empty records,
  and nested `replacement_history` from that segment, and never let it replace whole-session recovery.
- Require unexpected failures to return control to the model before a retry or workaround instead of
  pre-authoring an automatic fallback inside the same code-mode script.
- Remove the unreleased `0.4.0` experimental `PostToolUse` hook and its per-Bash transcript scan;
  rely on the compact-injected skill, which remains active until the next compaction and is then
  injected again.
- Emit a compact `0.4.1` runtime marker only for diagnosing which SessionStart version activated.

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
