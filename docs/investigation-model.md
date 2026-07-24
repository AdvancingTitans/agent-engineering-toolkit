# AET bounded investigation model

AET Quick combines deterministic evidence with bounded Agent investigation:

```text
user request
  -> command router
  -> intent resolver
  -> deterministic preflight
  -> hypothesis builder
  -> investigation planner
  -> authorized local/MCP tools
  -> investigation ledger
  -> dialectical reviewer
  -> grounding validator
  -> language-aware narrative renderer
  -> user decision
```

The model is designed around one separation: tools produce reproducible facts;
the LLM decides which relevant questions to investigate and may form an
explicitly grounded engineering judgment.

## Intent resolver

The resolver extracts the goal, explicit constraints, later authorization,
reasonable implicit permissions, prohibited high-risk actions, uncertain
terms, and source references. Every statement records whether it is
`explicit_user`, `explicit_project`, `inferred`, or `unknown`.

An inferred permission is never presented as explicit user authorization.
When missing intent prevents a scope conclusion, the command reports
`INSUFFICIENT_INTENT` while retaining any independently confirmed risks.

## Deterministic preflight

Preflight loads the smallest fact set relevant to the command: Git HEAD,
worktree state, changed files and hunks, manifests, CI definitions, project
instructions, available test commands, and relevant symbols or references.

Each observation has an identifier and tool invocation reference. Preflight
records observations only; it does not convert semantic relevance into fact.

## Hypothesis builder

For each material question, the LLM proposes:

- a primary explanation;
- a reasonable competing explanation;
- evidence capable of distinguishing the explanations;
- the result that would change the current judgment.

This requirement is dialectical, not numerical. A finding does not become
valid by accumulating a fixed count of weak evidence.

## Investigation planner

Every planned call states:

- the question being investigated;
- why the tool is needed now;
- which hypotheses the result can distinguish;
- expected decision value and cost;
- whether a cheaper method exists.

Calls are ordered by expected decision value, likelihood of obtaining a useful
answer, and cost:

1. current diff and symbol relationships;
2. local project documents and configuration;
3. narrow code search;
4. narrow tests;
5. bounded Git history;
6. allowlisted, read-only project MCP context;
7. full-repository analysis or other high-cost work.

The last tier requires explicit user authority. Remote writes, CI reruns, broad
external web research, complete test suites, and destructive actions never
inherit permission from a Quick read-only investigation.

## Investigation ledger

An investigation step counts as conclusion evidence only when it records a
question, tool input, immutable result reference, observation, hypothesis
effect, decision value, and cost.

Context reads without those links remain context, not evidence. Repeated calls
that do not alter a hypothesis are recorded but cannot be used to imply
stronger support.

The ledger preserves a canonical result payload and verifies its SHA-256
separately from the LLM narrative. This detects mutation inside the recorded
ledger. Except for `/aet-proof`, it is still a host attestation and does not
independently prove that an external MCP or local tool executed.

## Dialectical reviewer

The reviewer must provide:

1. the current best explanation;
2. its supporting evidence;
3. the material counter-explanation;
4. how that counter-explanation was checked;
5. remaining uncertainty;
6. evidence that could change the conclusion;
7. the smallest recommended action.

Facts, engineering judgments, and unresolved hypotheses remain distinct. A new
unverified concern is a `HYPOTHESIS`, never a blocking finding.

## Grounding validator

Deterministic grounding checks:

- every evidence and source reference exists;
- every cited invocation has a hash-valid recorded result;
- claims match tool results;
- negative claims identify the searched scope;
- user constraints have an intent source;
- test-pass claims have a recorded successful exit;
- freshness claims have a recorded comparison;
- material conflicting evidence is disclosed;
- conclusion strength does not exceed its evidence;
- recorded tools, reads, execution, writes, and declared usage stayed within
  authority and budget.

`CONFIRMED` requires a direct tool fact. `SUPPORTED` requires a checked
reasonable counter-explanation. An unchecked new issue remains a hypothesis.
Key conflict prevents an unqualified conclusion.

The validator does not claim that an engineering judgment is universally
correct. It rejects fabricated or broken recorded references, undisclosed
material conflicts already present in the Ledger, overstated conclusions, and
unauthorized actions. It cannot prove that an external Host executed an
attested call or discover counter-evidence that was never investigated.

The host must call `aet.investigation.validate_investigated_finding` before
rendering an investigated result. If the host cannot provide a valid Ledger,
Contract, and budget usage, it must preserve `HYPOTHESIS`/`UNKNOWN`.

## Investigation contract

Contracts specify mandatory investigation directions and grounding behavior,
not a fixed evidence count. A scope-expansion contract, for example, requires
intent recovery, changed-purpose identification, dependency inspection,
authorization search, and a counter-hypothesis.

Contracts prohibit:

- LLM similarity as sole evidence;
- treating an unexecuted test as passed;
- citing an unread file;
- hiding conflicting evidence;
- inferring unsupported authorization.

## Stop policy

Investigation stops when any condition applies:

- a dominant explanation exists and its reasonable counter-explanation has
  been checked;
- further results would not change the recommended action;
- two consecutive calls add no decision information;
- the command budget is exhausted;
- further work requires new user authority;
- only the user can supply the missing information;
- the required tool is unavailable.

The result discloses incomplete surfaces and remains bounded. Budget exhaustion
never implies that the repository was fully reviewed.

## Narrative renderer

The renderer uses progressive disclosure:

1. one-sentence conclusion;
2. confirmed facts;
3. engineering judgment;
4. counter-explanation and investigation result;
5. remaining uncertainty;
6. precise file, behavior, or contract location;
7. smallest actionable next step;
8. expandable raw evidence references.

Simplified Chinese output uses natural engineering language rather than literal
translations, while retaining necessary English code and technical terms.
English is the default outside a Chinese slash-command request. Both renderers
consume the same facts and statuses and must remain semantically equivalent.
