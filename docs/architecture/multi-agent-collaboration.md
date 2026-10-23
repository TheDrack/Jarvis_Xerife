# Multi-agent collaboration protocol

Jarvis is evolving into a harness that can connect to local or cloud models and other harnesses. Cross-agent collaboration should be an explicit protocol, not an implicit shared chat or shared mutable working tree.

## Recommended pattern

Use an **orchestrator + bounded workers + shared artifact ledger**. The coordinator owns task decomposition and integration. Workers own disjoint, clearly named outputs. A reviewer independently verifies claims and tests. The ledger stores status and references to durable artifacts. This combines the bounded orchestration described by Anthropic with the persistent artifacts needed for multi-turn repository work.

## Initial implementation policy

- One active writer per file/branch; use separate branches/worktrees for parallel changes.
- Each task carries scope, owner, allowed paths, dependencies, acceptance criteria, validation, and artifact references.
- Chat messages are not the source of truth; store task state and results in the repository or a trusted shared service.
- Cap delegation depth, retries, tool calls, and concurrency. Avoid recursive agent spawning and duplicate work.
- Use explicit review gates before integration. A successful test report must include the command and actual result.
- Keep identity, authentication, authorization, and tool execution rights separate across harnesses.
- Never expose remote desktop-control tools without authentication and least-privilege authorization. Do not assume Tailscale membership or Host/Origin validation alone is sufficient authentication.

## Human checkpoints

Require user approval for secret handling, new external access, destructive actions, production deployment, merging/releasing, or any permission expansion not already authorized.

## References

- Anthropic, *How we built our multi-agent research system*: https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, *Multi-agent coordination patterns*: https://claude.com/resources/articles/multi-agent-coordination-patterns
- OWASP, *MCP Security Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- OWASP, *MCP Secure Development Guide*: https://github.com/OWASP/MCP-Security-Testing-Guide/blob/main/04.%20Secure%20MCP%20Development.md
