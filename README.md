# retail-intelligence
Nvidia Spark Hack 2026

## Implement Linear issues with Codex cloud

The repository uses the native Codex for Linear integration. Assigning a Linear issue to Codex or
mentioning `@Codex` in an issue comment starts an isolated Codex cloud chat. Codex reports progress
in Linear and returns a completed chat with a diff for human review.

### One-time setup

1. In [Codex](https://chatgpt.com/codex), connect GitHub and grant access to
   `wibe-coders/retail-intelligence`.
2. In [Codex environment settings](https://chatgpt.com/codex/settings/environments), create an
   environment whose first repository is `wibe-coders/retail-intelligence`. No setup script is
   currently required; add pinned runtimes and dependency installation when the repository gains a
   package manifest.
3. In [Codex settings](https://chatgpt.com/codex/settings), install Codex for Linear for the
   workspace.
4. Mention `@Codex` on a Linear issue once to link the Linear and ChatGPT accounts.

See the official [Codex for Linear](https://learn.chatgpt.com/docs/third-party/linear) and
[cloud environment](https://learn.chatgpt.com/docs/environments/cloud-environment) documentation.

### Delegate work

- Assign an issue to Codex to start implementation.
- Mention `@Codex` in a comment to give task-specific direction or continue the same cloud chat.
- Include `wibe-coders/retail-intelligence` in the comment when repository selection could be
  ambiguous.
- Do not start a second Codex assignment while one is already active on the same issue.
- To assign eligible issues automatically, enable Triage for the Linear team and add a triage rule
  whose action is **Delegate > Codex**. The task runs against the issue creator's connected ChatGPT
  account, so use automatic delegation only for members who have linked accounts and repository
  access.

Codex follows [AGENTS.md](AGENTS.md) for implementation, testing, security, and reporting. If it
cannot finish or a required check fails, it must return the partial work and blocker for inspection.
When work is complete, review the diff in the linked cloud chat and create a pull request from
there. A person must review and merge it.

Codex must never push `main` or another mainline branch. It may commit locally and push an explicitly
named non-mainline branch; the repository owner promotes changes to `main`.
