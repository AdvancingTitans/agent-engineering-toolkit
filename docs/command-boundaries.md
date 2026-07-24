# AET Quick command boundaries

This document freezes the user-facing boundary of AET Quick. Quick exposes four
independent slash-command Skills. Each command answers one primary question,
stops after reporting, and never starts another Quick command or AET Lab flow
unless the user explicitly requested that composition.

The host Skill owns natural-language intent resolution, bounded LLM reasoning,
and authorized MCP/tool orchestration. The Python CLI remains the
deterministic evidence, execution, freshness, and grounding runtime. LLM output
is never allowed to rewrite tool facts, hide conflicting evidence, or authorize
merge, push, release, publication, or governance adoption.

## Shared status model

AET preserves `PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE` as the
authoritative evidence status. Quick commands add a separate
`assessment_state` for command-specific meaning. An assessment state cannot
silently turn an authoritative `UNKNOWN` into `PASS`.

Findings identify their origin:

- `DETERMINISTIC_FINDING`: directly produced by a rule, test, or tool fact.
- `INVESTIGATED_FINDING`: an LLM engineering judgment grounded in referenced
  tool results and a checked counter-explanation.
- `HYPOTHESIS`: an unverified investigation direction; it is never a blocking
  finding.

## Language

When a user invokes a slash command and asks in Simplified Chinese, the host
renders the narrative in natural Simplified Chinese while preserving code,
paths, commands, identifiers, and necessary technical terms in English. In all
other cases the narrative language is English. Language selection
cannot change facts, statuses, evidence references, or recommended actions.

## `/aet-check`

Primary question: are the repository's Agent instructions, Skills, verification
claims, and AI-maintenance boundaries executable and safe enough for the
declared task?

Default read surface:

- root Agent instruction files, including `AGENTS.md`, `CLAUDE.md`, and
  equivalent supported files;
- `.agents/skills/**`, `.claude/skills/**`, and the canonical Skill surface;
- README, package manifests, test configuration, CI workflows, and
  task-specific configuration.

Default exclusions:

- complete Git history;
- all source files;
- credentials and private configuration;
- unrelated generated directories.

The command performs deterministic preflight, investigates no more than three
core hypotheses, checks material counter-explanations, emits no more than five
high-value findings, and stops.

Default budget:

- target wall time: 30 seconds;
- investigation rounds: at most 3;
- high-cost calls: at most 1;
- LLM calls: 1 primary call and, only when necessary, 1 follow-up;
- writes: none;
- project-code execution: none by default.

## `/aet-scope`

Primary question: are the current changes necessary for, and authorized by, the
user's task?

Intent sources, in descending priority:

1. the user's original request in the current conversation;
2. later user authorization;
3. an explicit Intent file;
4. Issue or PR description;
5. commit message;
6. an explicitly labelled inference when no stronger source is available.

The command groups changes by functional purpose, proposes competing necessity
hypotheses, and uses changed paths, diff hunks, symbol references, dependency
relationships, tests, project constraints, and bounded history or remote
project context to distinguish them.

A path outside an allowlist is not sufficient by itself to establish
`OUT_OF_SCOPE`. The investigation must consider shared infrastructure,
interface migration, generated or formatting-only changes, later
authorization, and whether a smaller implementation could satisfy the task.

Assessment states:

- `IN_SCOPE`;
- `JUSTIFIED_EXPANSION`;
- `POSSIBLE_SCOPE_EXPANSION`;
- `OUT_OF_SCOPE`;
- `INSUFFICIENT_INTENT`.

Default budget:

- target wall time: 45 seconds;
- investigation rounds: at most 4;
- tool calls: at most 8;
- allowlisted, read-only remote MCP calls: at most 2 and only when local
  evidence is insufficient and the result may change the decision;
- high-cost calls: at most 1;
- one low-cost discriminating test may run only within the command's explicit
  execution authority;
- full test suites and code mutation: disabled by default.

Remote writes and unallowlisted remote access always require separate user
authority. Quick never uses remote access merely to make a report look more
complete.

## `/aet-proof`

Primary question: did a specific validation command actually run, and what
code, workspace, environment boundary, and declared artifacts does that result
cover?

The LLM may locate the repository's recommended command, select the smallest
relevant validation set, and propose declared artifacts. The deterministic
runtime alone records argv, cwd, timestamps, exit code, redacted output
digests, Git HEAD, worktree digest, relevant-path bindings, declared artifact
bindings, and provenance.

Calling `/aet-proof` is the sole Quick write exception: the explicit command
authorizes writing one minimal JSON proof receipt to the supplied or accepted
output path. It does not authorize source edits, HTML/SVG/viewer generation,
full-suite escalation, or any other write.

Environment binding is deliberately bounded. The receipt records available
runtime identifiers needed by the selected command, lockfile hashes, operating
system identity, and only the names and redacted/hash-bound values of
environment inputs explicitly declared for the proof. It never captures the
ambient environment or secrets by default. An unavailable required binding is
`UNKNOWN`, not guessed.

An exit code of zero proves only the recorded command completed successfully.
The narrative must state the exact validation surface and must not claim that
an unexecuted broader suite passed.

## `/aet-fresh`

Primary question: can an existing proof still describe the current code and
declared validation boundary?

Deterministic checks compare:

- Git HEAD and worktree state;
- relevant file bindings;
- dependency and lockfile bindings;
- declared artifact bindings;
- recorded key runtime and explicitly declared environment bindings.

Assessment states:

- `EXACT_MATCH`;
- `RELEVANT_FILES_MATCH`;
- `HEAD_CHANGED_RELEVANT_FILES_MATCH`;
- `RELEVANT_FILES_CHANGED`;
- `ARTIFACT_CHANGED`;
- `ENVIRONMENT_CHANGED`;
- `UNKNOWN`.

The default path uses no LLM, network, or writes and targets three seconds.
When the user asks for an impact explanation, one LLM call may explain which
coverage is stale and the smallest validation to rerun. It cannot decide
whether a file or binding changed.

## Bounded-result behavior

When a budget, permission boundary, missing user fact, or unavailable tool
stops an investigation, AET emits a bounded result. It lists uninspected
surfaces, distinguishes facts from inferences, explains whether the missing
information could change the recommended action, and never silently escalates
to a deeper audit.
