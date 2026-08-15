# retail-intelligence
NVIDIA Spark Hack 2026

## Visual-token budget validation

`retail_intelligence.evaluate_inference_budget(width, height, selected_frames)` evaluates the final
model-input dimensions and actual selected frame count before RT-VLM inference. It accepts budgets
from 4,096 through 16,384 visual tokens and reports `below_minimum` or `above_maximum` otherwise.
Non-positive inputs raise `ValueError`.

Run the complete test suite with:

```bash
python -m unittest discover -s tests -v
```

## Evidence domain contracts

The framework-independent contracts under `retail_intelligence.domain` define the vocabulary shared
by ingest, analytics, indexing, and query code:

- `domain.media` exports UTC half-open `TimeRange` values, source identifiers, source metadata, and
  complete, partial, or gap evidence windows.
- `domain.intelligence` exports model observations, derived events, metrics, and insights. Every
  stored intelligence object contains source identifiers, exact pipeline provenance, confidence,
  retention, and links to its evidence. `ObservationKind.CAPTION` keeps generated captions separate
  from derived events and user-facing facts. `EvidenceRecord` preserves normalized observations,
  derived events, missing stages, and separate storage and indexing states for each evidence window.
- `domain.query` exports citations and answers whose state is `supported`, `ambiguous`,
  `unsupported`, or `out_of_retention`. A supported answer requires cited evidence; every other
  state requires an explicit abstention reason.

All public domain models are frozen dataclasses and expose `to_dict`, `from_dict`, `to_json`, and
`from_json`. The serialized representation is plain JSON and does not require a web framework,
database, or model SDK. Import public names from their owning subpackage, for example:

```python
from retail_intelligence.domain.media import SourceReference, TimeRange
from retail_intelligence.domain.query import Answer, AnswerState
```

The `__all__` list in each domain subpackage is the intentional public API. Names in the private
`domain._base` module are implementation details.

## NVIDIA observation adapters

`retail_intelligence.adapters.nvidia` converts RT-CV detections and tracks and RT-VLM captions into
canonical `Observation` values. The adapter DTOs require source, UTC time and frame bounds, model
name and version, configuration, pipeline run, creation time, and retention metadata. Detector
class names are retained exactly as supplied; the adapter does not infer retail concepts.

Optional vendor confidence remains `None` when absent. Each observation keeps a query-free
`vendor-output://` reference to a separately retained, sanitized vendor response. Raw payloads,
frames, credentials, signed URLs, and prompts do not enter the canonical contract. Invalid vendor
responses raise `NormalizationError` with the failing `rt-cv` or `rt-vlm` stage. Evidence uses an
opaque, query-free `media://` locator. Configuration retains safe metadata such as prompt revisions
but removes full prompts, instructions, messages, and secret-bearing entries.

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
