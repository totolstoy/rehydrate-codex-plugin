# Security

## Reporting a vulnerability

Use GitHub's private security advisory feature for vulnerabilities. Do not include private Codex
transcripts, credentials, session files, or other sensitive data in a public issue.

## Security boundaries

- Rehydrate's hook scripts do not make network requests.
- The skill reads only relevant records across the session and does not load the complete transcript
  by default.
- Recovery is limited to user-visible messages and observable assistant actions. The skill must not
  inspect, extract, summarize, or expose hidden reasoning, reasoning summaries, encrypted content,
  credentials, or unrelated sensitive data.
- Historical transcript content and tool output are untrusted evidence, not a source of current
  instructions.
- Tool calls must be paired with results, and planned, failed, aborted, or rolled-back work must not
  be treated as completed work.
- Execution-time lookups are targeted checks at material action boundaries, not continuous transcript
  monitoring. A lookup should occur only when prior evidence could change the next action.
- Hook execution remains subject to user approval, Codex permissions, and workspace policy.

The plugin cannot override Codex sandboxing, managed policy, or filesystem permissions.
