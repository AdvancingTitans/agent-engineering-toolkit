# GitHub Actions

The template under `integrations/github-action-template/` is intended for a
separate public Action repository. It supports only read-only `check`, `scope`,
and `fresh` modes.

It does not run arbitrary proof commands. On fork pull requests, never expose
secrets to untrusted code or use `pull_request_target` to execute the fork.
Pin the AET package version exactly; security-sensitive consumers should pin
the Action commit SHA.

To execute a proof, write an explicit workflow step in a repository you
control, then pass the resulting proof to `fresh`.
