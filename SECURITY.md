# Security

## Reporting a vulnerability

Use GitHub's private security advisory feature for vulnerabilities. Do not include private Codex
transcripts, credentials, session files, or other sensitive data in a public issue.

## Security boundaries

- Rehydrate's hook scripts do not make network requests.
- The skill reads only relevant records across the session and does not load the complete transcript
  by default.
- The bundled query helper is local and read-only. It performs no network access, creates no sidecar
  index, and emits valid bounded JSON with explicit continuation or incomplete-state markers.
- Recovery is limited to user-visible messages and observable assistant actions. The skill must not
  inspect, extract, summarize, or expose hidden reasoning, reasoning summaries, encrypted content,
  credentials, or unrelated sensitive data.
- The final meaningful pre-compaction segment is selected from top-level, user-visible messages and
  observable actions. Synthesized summaries, hook, skill, and environment wrappers, lifecycle telemetry, empty
  records, and nested `replacement_history` are excluded. The tail supplements rather than replaces
  whole-session recovery.
- Historical transcript content and tool output are untrusted evidence, not a source of current
  instructions.
- Tool calls must be paired with results, and planned, failed, aborted, or rolled-back work must not
  be treated as completed work.
- Terminal status is accepted only from the outer response status, top-level structured result
  fields, or a recognized execution envelope. Nested `error` or `exit_code` fragments in logs do not
  override the outer result.
- Recovery associates the governing user turn through `turn_id`, immediate call/results through
  `call_id`, and yielded commands through observable opaque `cell_id` and numeric `session_id`
  handles across later turns and explicit cross-compaction continuations until terminal status.
  Completed chains are not joined to later handle reuse. Running and unpaired actions are never
  treated as verified success.
- Candidate pages and previews are anchors rather than complete evidence. Fixed page sizes are
  transport boundaries, not semantic stopping rules. When a result is truncated or incomplete, the
  Agent must narrow the compaction window, turn, operation, target, call, handle, or stable error
  intersection instead of increasing a broad output limit.
- `search` keeps semantic line bounds separate from its action-chain continuation cursor, so later
  evidence cannot retroactively alter a bounded earlier-state query and interleaved chains remain
  atomic across pages.
- Prior history-query calls and echoed output are excluded from ordinary evidence search, preventing
  recursive matches. Direct POSIX and PowerShell transcript readers are treated the same way, while
  ordinary project and documentation searches remain evidence. Explicit query-mechanism diagnostics
  expose only structure and status, not the echoed body or embedded handles. Each history query must
  run separately from task commands so exclusion cannot hide a mixed operation.
- Execution-time lookups are targeted checks at material action boundaries, not continuous transcript
  monitoring. After a material failure, the skill must run one targeted earlier-session lookup before
  the first retry or workaround, even if the summary suggests an obvious fix, and follow matching
  failures through to the most recent verified success. It may reuse only a lookup performed since
  activation for the same operation, target, and error-signature key. It must revalidate mutable
  prerequisites before reusing an old fix and must not rescan the same key after repeated failures.
- A deliberate probe bypasses failure recovery only when its negative result is an expected, accepted
  branch with both a predefined interpretation and a predefined next step.
- Unexpected failures must return control to the model before a retry or workaround. A retry must not
  be pre-authored in the same code-mode script unless it is an expected probe branch.
- The failure checkpoint is a model-level contract in the compact-injected skill, not a per-tool hook
  or mechanical enforcement boundary. The compact hook reinjects that contract after every later
  compaction.
- Hook execution remains subject to user approval, Codex permissions, and workspace policy.
- Hidden reasoning, encrypted content, developer wrappers, nested `replacement_history`, and common
  credential forms, including CLI options, are filtered before matching or output. Unknown or
  malformed content-block lists fail closed and are not recursively stringified.

The plugin cannot override Codex sandboxing, managed policy, or filesystem permissions.
