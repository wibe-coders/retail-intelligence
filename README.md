# retail-intelligence
Nvidia Spark Hack 2026

## Autonomous issue implementation

Issues created by `varun10p`, `VishnuKartha`, `visirion07`, or `nTamilselvan` can trigger the dedicated
EC2 Codex runner when any of those trusted users applies one of these labels:

- `auto` implements the issue and pushes `codex/issue-N`. It does not open a pull request or change
  `main`.
- `supervised` implements the issue, pushes the same branch, and opens or updates a pull request to
  `main`. A person must review and merge it. If both labels are present, `supervised` wins.

Removing and reapplying either label resumes the same branch. Updating the issue without applying a
label does not start a run. Untrusted issue authors and label actors are rejected before a job is
assigned to the self-hosted runner.

The full implementation, testing, documentation, and failure procedure is in [AGENTS.md](AGENTS.md).
If Codex cannot finish, a rebase conflicts, or required checks fail, the workflow pushes a WIP commit
when one exists, comments on the issue, and leaves the issue open. Partial supervised work is opened
as a draft pull request.

The runner is named `retail-intelligence-codex-ec2` and requires the custom
`retail-intelligence-codex` label. Its ChatGPT login is stored only under the non-sudo runner account
on the disposable EC2 host. The workflow does not pass a GitHub token to Codex; only the publishing
step receives one. Do not target this runner from pull-request workflows or workflows editable by
untrusted contributors.

Codex must never push `main` or another mainline branch. It may commit locally and push named feature
branches; the repository owner promotes changes to `main`. The EC2 publisher independently enforces
the `codex/issue-N` branch shape and refuses to push when any other branch is checked out.
