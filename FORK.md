# Fork notes

This repository is a fork of [`o11y-dev/opentelemetry-hooks`](https://github.com/o11y-dev/opentelemetry-hooks)
(MIT) that adds **IBM Bob** as a supported agent.

Because the upstream lives on github.com and this fork lives on an IBM
GitHub Enterprise instance, GitHub's own fork mechanism cannot link them. The
relationship is maintained through a plain `upstream` remote instead.

## Remotes

```
origin    → https://github.ibm.com/Ryo-Nakayama/opentelemetry-hooks-bob.git   (private)
upstream  → https://github.com/o11y-dev/opentelemetry-hooks.git               (fetch only)
```

`upstream` has its push URL deliberately disabled so a stray `git push upstream`
cannot reach the public repository. Reproduce that after a fresh clone with:

```bash
git remote add upstream https://github.com/o11y-dev/opentelemetry-hooks.git
git remote set-url --push upstream DISABLED_use_origin
```

## Branches

- `main` — kept at upstream parity, no fork changes. Merge `upstream/main` here.
- `feat/bob-adapter` — the IBM Bob work.

## Syncing with upstream

```bash
git fetch upstream
git checkout main
git merge upstream/main        # or: git rebase upstream/main
```

## What this fork changes

All Bob support is additive — it plugs into upstream's existing provider-adapter
extension points rather than modifying shared behavior. The touch points:

| Area | Change |
|---|---|
| `otel_hook.py` | `BobEventAdapter`, `BobHookResponseAdapter`, `setup_bob`, `policy` command, Bob entries in the detection, path, and CLI tables |
| `setup.sh` | `--bob` flag with setup / diagnose / uninstall / clean |
| `tests/` | `test_bob.py`, `fixtures/contracts/bob.json`, capability manifest entry |
| `examples/` | `bob-hooks.example.json`, `bob-enforced-hooks.example.json` |
| `README.md`, `CHANGELOG.md`, `pyproject.toml` | Bob documentation and metadata |

One upstream file is changed for a non-Bob reason:

- `tests/test_contracts.py` — the shared fixture harness gained optional
  `lifecycle_data` / `lifecycle_data_absent` assertions so a provider's field
  renames can be asserted from its fixture. This is provider-neutral.

One upstream behavior is corrected:

- `_detect_payload_client_name` treated any PascalCase event name as Claude Code,
  which claimed Bob's lifecycle names. Bob is now discriminated on the bare
  `event` key, which Claude Code does not use.

See `CHANGELOG.md` for the full list.

## Upstreaming

The changes are deliberately shaped as an additive provider adapter, so they can
be offered upstream as a pull request. To produce a patch against upstream:

```bash
git fetch upstream
git format-patch upstream/main..HEAD
```

Note that the Bob-specific documentation in `README.md` and the examples cite
IBM Bob's product documentation; review what is appropriate to publish before
opening a public pull request.
