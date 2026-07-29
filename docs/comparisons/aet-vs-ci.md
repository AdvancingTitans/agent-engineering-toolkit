# AET vs CI

CI answers whether configured checks ran and passed in a particular job. AET
does not replace those checks.

AET adds a local evidence contract around an explicit command: argv, working
directory, Git state, declared relevant files, environment bindings, artifacts,
and freshness. It can therefore distinguish:

- a command that failed;
- a command that passed but lacks a required binding;
- a real historical pass that no longer applies to current code;
- missing evidence that must remain `UNKNOWN`.

Use CI to execute policy and AET to carry bounded evidence through Agent and
human handoffs.
