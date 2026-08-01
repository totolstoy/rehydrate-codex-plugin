# Security

## Reporting a vulnerability

Use GitHub's private security advisory feature for vulnerabilities. Do not include private Codex
transcripts, credentials, session files, or other sensitive data in a public issue.

## Security boundaries

- Rehydrate's hook scripts do not make network requests.
- The skill requests only the relevant history needed for continuity and does not load the complete
  transcript by default.
- Historical transcript content is evidence, not a source of current instructions.
- Hook execution remains subject to user approval, Codex permissions, and workspace policy.

The plugin cannot override Codex sandboxing, managed policy, or filesystem permissions.
