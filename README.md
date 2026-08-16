# retail-intelligence

Retail Intelligence turns retail CCTV into evidence-backed observations and lets authorized users
ask questions about them in plain language. Runtime video and queries stay on one DGX Spark, and
answers link back to the supporting camera and time range.

This project is being developed for NVIDIA Spark Hack 2026.

## DGX Spark smoke-test video

The repository includes one approved short video for the first real RT-VLM inference run. It shows
a distant person walking through an indoor shopping passageway; its expected coarse observations,
source, license, and transformation are recorded in [samples/README.md](samples/README.md).

Install `ffmpeg` and run the complete checksum, metadata, decode, frame-sampling, and visual-token
preflight with one command:

```bash
python3 scripts/preflight_smoke_video.py
```

Do not start the Spark inference run unless every check prints `PASS`.

The completed DGX Spark result, pinned standalone RT-VLM setup, and exact repeat commands are in
[the RET-56 smoke-test report](docs/ret-56-dgx-spark-smoke-test.md).

## Project documentation

- [Product and architecture specification](spec/agent.md)
- [Evidence contracts](spec/evidence-contracts/agent.md)
- [Data pipeline specification](spec/data-pipeline/agent.md)
- [NVIDIA adapter specification](spec/nvidia-adapters/agent.md)
- [Synthetic convenience-store inventory](evals/datasets/synthetic-convenience-store-v1/README.md)
- [Retail video dataset review](docs/retail-video-datasets.md)

The dataset review compares candidate evaluation data, usage terms, leakage risks, and
task-specific recommendations. It does not authorize dataset use or redistribution.

## Development

Run the complete test suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Application packages live under `src/`; repository commands must add that directory to the Python
import path until the project gains an installable package manifest.

## Implement Linear issues with Codex cloud

The repository uses the native Codex for Linear integration. Assigning a Linear issue to Codex or
mentioning `@Codex` in an issue comment starts an isolated Codex cloud chat. Codex reports progress
in Linear and returns a completed chat with a diff for human review.

### One-time setup

1. In [Codex](https://chatgpt.com/codex), connect GitHub and grant access to
   this repository.
2. In [Codex environment settings](https://chatgpt.com/codex/settings/environments), create an
   environment whose first repository is this repository. No setup script is currently required;
   add pinned runtimes and dependency installation when the repository gains a package manifest.
3. In [Codex settings](https://chatgpt.com/codex/settings), install Codex for Linear for the
   workspace.
4. Mention `@Codex` on a Linear issue once to link the Linear and ChatGPT accounts.

See the official [Codex for Linear](https://learn.chatgpt.com/docs/third-party/linear) and
[cloud environment](https://learn.chatgpt.com/docs/environments/cloud-environment) documentation.

### Delegate work

- Assign an issue to Codex to start implementation.
- Mention `@Codex` in a comment to give task-specific direction or continue the same cloud chat.
- Include this repository's full GitHub URL in the comment when repository selection could be
  ambiguous.
- Do not start a second Codex assignment while one is already active on the same issue.

### Start tasks without a comment

Linear can delegate new issues without an assignment or `@Codex` comment:

1. Open the team's Linear settings and enable **Triage** under workflow settings.
2. Add a triage rule for eligible issues with the action **Delegate > Codex**.
3. Create an issue that enters Triage and matches the rule.

After the one-time account link, the matching issue starts a Codex cloud task automatically. Use a
narrow rule, such as a dedicated `codex` label or project, until the flow is proven. Automatic tasks
run with the issue creator's connected ChatGPT account, so each eligible creator must have linked
accounts and access to the repository and its Codex environment.

This automates task kickoff, not approval. Codex returns a completed cloud chat and diff. A person
reviews the change, creates the pull request from the chat, and merges it.

### Troubleshooting

- **No available environments:** create or share a Codex cloud environment in the same ChatGPT
  workspace as the Linear integration, and make this repository its first repository. Retry the
  issue after the environment is visible to the issue creator's account.
- **`make_pr` is unavailable:** this repository intentionally has no `make_pr` command. The task
  should finish with its verified diff; create the pull request from the completed Codex cloud chat.

Codex follows [AGENTS.md](AGENTS.md) for implementation, testing, security, and reporting. If it
cannot finish or a required check fails, it must return the partial work and blocker for inspection.

Codex must never push `main` or another mainline branch. It may commit locally and push an explicitly
named non-mainline branch; the repository owner promotes changes to `main`.
