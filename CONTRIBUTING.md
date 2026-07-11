# Contributing to AET

Thanks for considering a contribution. AET is intentionally small: evidence
must be inspectable, local behavior must be deterministic by default, and an
`UNKNOWN` must never be marketed as a pass.

## Good ways to help

- Report a reproducible false positive, false negative, or unsafe boundary.
- Contribute a small positive/negative fixture for a rule or evidence contract.
- Share an anonymized, reproducible AET workflow from a real coding-agent
  handoff or repository-onboarding task.
- Improve the English or Chinese documentation, examples, or accessibility.

Please search existing [Issues](https://github.com/AdvancingTitans/agent-engineering-toolkit/issues)
first. Use the Bug Report or Feature Request form so maintainers can reproduce
the question without requesting sensitive repository contents.

## Local development

```bash
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
uv run --no-editable --reinstall-package agent-engineering-toolkit python -m unittest discover -s tests -v
uv run --no-editable aet audit . --strict
```

Use Python 3.11 or later. The project intentionally uses the standard library
for its runtime behavior; please discuss a new dependency before adding one.

## Pull request expectations

1. Start from a focused Issue for non-trivial changes.
2. Keep the change narrow and explain the user-facing evidence boundary.
3. For behavior changes, add both a passing and failing regression case.
4. Run the commands above. For distribution changes, also run `uv build` and
   smoke-test the generated wheel in an isolated environment.
5. Update documentation, contracts, and `CHANGELOG.md` when public behavior
   changes.

For agent-authored changes, create a focused `aet.intent.json` and run
`aet review . --base main`. If you execute a proof command, use `aet trace`
with an explicit `--proof` binding. Do not attach raw secrets, unredacted logs,
or private repository history to an Issue or pull request.

## Scope and design principles

- Prefer a direct finding with source evidence over a broad trust score.
- Keep `audit`, `review`, local `evolve`, and triage read-only.
- Preserve explicit opt-in for generic command execution and remote retrieval.
- Make unsupported facts `UNKNOWN`; do not infer private author intent.
- Prefer a small, tested rule over a speculative framework.

By contributing, you agree that your contributions are available under this
repository's [MIT License](LICENSE).
