# Changelog

## Unreleased (fork: IBM Bob support)

### Added
- Added IBM Bob as a supported agent: a `BobEventAdapter` that maps Bob's `tool`/`input`/`output` fields onto the shared `tool_name`/`tool_input`/`tool_output` contract, scoped to `PreToolUse`/`PostToolUse` so `output` is not mistaken for a shell stdout stream and `input` does not shadow the `UserPromptSubmit` prompt key.
- Added `otel-hook setup --agent bob`, `otel-hook --bob`, and Bob support in `diagnose`, `doctor`, and `uninstall`, writing `~/.bob/settings/settings.json` or `.bob/settings.json` with `matcher` on the two tool callbacks only.
- Added `otel-hook policy --bob` to generate the value for Bob's `enforcedHooks` group policy, with `--hook-cmd` for the managed absolute path, `--raw` for a paste-ready single line, `--escaped` for nesting in another document, and a stderr warning when the command resolves through `PATH`.
- Added `bash setup.sh --bob` with matching diagnose, uninstall, and clean support.
- Added a Bob provider contract fixture, a capability manifest entry, and `tests/test_bob.py` covering stdout silence, field mapping, detection, setup, and policy generation.
- Added optional `lifecycle_data` and `lifecycle_data_absent` assertions to the shared provider contract fixture harness so field renames are verifiable from a fixture.

### Changed
- Made Bob hooks silent on stdout for every event. Bob injects hook stdout into the model context for `SessionStart` and `UserPromptSubmit` and has no stdout response contract, so the usual `{"continue": true}` envelope would land in the prompt on every turn. Bob hooks always exit 0 and never block.
- Registered Bob's hooks with an explicit `timeout: 30` instead of Bob's 10-second default, which a cold Python start plus an OTLP flush can exceed. Bob only logs a hook timeout, so a short value drops telemetry silently.

### Fixed
- Stopped an explicitly declared agent from being relabelled by payload shape heuristics. `tool_response` and `last_assistant_message` are sent by Claude Code, IBM Bob and Codex alike, but `_detect_payload_client_name` treated them as strong Codex signals, so **every** `PostToolUse` span was exported as `gen_ai.client.name=codex` — for Claude Code as much as for Bob, and reproducible on upstream v0.14.0. When the caller declared the agent (`otel-hook --<agent>`, `IDE_OTEL_HOOK_SOURCE`, or `IDE_OTEL_IDE_NAME`), that now wins over an inferred engine; an engine the payload names outright still takes precedence, so genuine nested agents are unaffected. Verified against a live Bob turn: all five spans of one turn now agree on `bob`, where before `PostToolUse` alone said `codex`.
- Routed the `IDE_OTEL_DEBUG_CONSOLE` span and log console exporters to stderr for runners whose stdout is model-visible. OpenTelemetry's console exporters default to stdout, so enabling debug output under Bob would have pasted span JSON into the prompt. Providers now declare this through `HookResponseAdapter.stdout_is_model_visible`, so the protection follows the adapter rather than a hardcoded provider check.
- Stopped `_detect_payload_client_name` from claiming Bob payloads as Claude Code. Its generic "PascalCase event name means Claude" rule matched Bob's lifecycle names; Bob is now discriminated on the bare `event` key that Claude Code does not use.

### Notes
- Bob has no `SessionEnd`. Its `Stop` is a turn boundary, so it maps to generation end and is deliberately not mapped to `SessionEnd`; the session root span is emitted by the existing stale-session TTL flush. Lower `IDE_OTEL_STATE_TTL_SECONDS` for Bob deployments.

## 0.14.0 (2026-07-22)

### Added
- Added a canonical hook event model with provider adapters for Cursor, Windsurf, Claude, Codex, Gemini, Antigravity, Copilot, and OpenCode.
- Added span-first prompt, response, stop-message, error, and delegation facts with length and SHA-256 metadata by default and explicit content capture through `IDE_OTEL_CAPTURE_CONVERSATION_CONTENT`.
- Added stable session-backed subagent identities, parent relationships, delegation status, and trace links when valid source contexts are available.
- Added workspace, repository root, credential-free Git remote hashing, branch identity, hook schema/source provenance, and native trace/span identifiers.
- Added `otel-hook doctor` with human and JSON reports for registrations, privacy controls, exporter health, pending state, and sanitized delivery failures.
- Added sanitized provider contract fixtures and a capability manifest for every supported agent family.

### Changed
- Extended session-backed idempotency to prompts, errors, subagents, compaction, and permission callbacks while retaining bounded state and lifecycle cleanup.
- Made spans the authoritative conversation signal. Optional trace-correlated conversation logs require `IDE_OTEL_ENABLE_CONVERSATION_LOGS=true`.
- Decorated OTLP exporters with bounded delivery-health recording that excludes payloads, headers, credentials, and raw error messages.
- Split callback deduplication, tool/MCP correlation, and subagent FIFO correlation into focused session-backed services, and made the typed canonical contract privacy-safe before lifecycle processing.

### Fixed
- Prevented human-readable `otel-hook doctor` fallback reports from raising a second exception when diagnostics fail internally; both human and JSON modes now return sanitized error-type evidence.
- Prevented raw prompt, error, and delegation content from bypassing privacy gates through direct event attribute mappings.
- Preserved native and hook telemetry as distinct sources while linking valid native contexts instead of deduplicating them.
- Reserved generic trace fields for upstream parenting and required explicit native trace/span fields for native attributes and links.
- Prevented successful trace batches from replaying when only the optional log pipeline fails; doctor now reports failures from any enabled exporter signal.
- Preserved legitimate concurrent identical subagent starts while keeping provider-ID callbacks idempotent and correlating no-ID stops in FIFO order.
- Emitted correlated Cursor MCP lifecycle evidence as authoritative spans in streaming mode, including when logs are disabled, while retaining the stable generic tool ID.
- Normalized Cursor dedicated MCP durations from seconds to milliseconds and set real failure spans to OpenTelemetry `ERROR` while leaving intentional interrupts `UNSET`.
- Stopped inventing workspace identity from the hook process's current directory when an event provides no workspace or repository evidence.

## 0.13.6 (unreleased)

### Added
- Added explicit cross-agent MCP server/tool attributes for encoded Codex and Claude tool names and Cursor's `mcp_server_name` payloads.
- Added `telemetry.distro.name` and `telemetry.distro.version` hook provenance without changing agent service identity or version fields.
- Preserved OTel resource attributes in local JSON spans so installed hook provenance remains inspectable without an OTLP backend.

### Changed
- Encapsulated bounded tool deduplication and provider-specific invocation matching in a session-aware MCP correlator.
- Made session creation, callback deduplication, generic/dedicated Cursor MCP correlation, and pending-generation ownership session-scoped and atomic across hook processes.
- Made `Stop` flush only the current generation while preserving the session, and made `SessionEnd` or stale finalization flush every session-owned batch exactly once before cleanup.

### Fixed
- Prevented duplicate Cursor callbacks and dedicated MCP events from creating duplicate logical tool spans, while reusing the stable generic `tool_use_id` for correlated evidence.
- Correlated unambiguous Codex `PermissionRequest` callbacks with their open tool invocation and preserved Claude failure IDs and status.
- Prevented stale-session cleanup from deleting pending Codex batches before their generation and session spans can be exported.
- Suppressed duplicate generation `Stop` callbacks and preserved correlated Cursor MCP evidence in streaming mode without creating duplicate logical generic tool spans.
- Routed stale-finalized session roots to their own local JSON files instead of the cleanup trigger's `unscoped.jsonl` file.

## 0.13.5 (2026-05-25)

### Fixed
- Removed project-directory (`.cursor`/cwd) checks from agent-engine inference and consolidated engine detection paths to avoid weak, environment-dependent relabeling.

## 0.13.4 (2026-05-20)

### Fixed
- Preserved native Cursor client attribution for Cursor-style payloads when leaked Claude-specific hints would otherwise misclassify the event, while still recording any distinct wrapper via `gen_ai.client.wrapper`

## 0.13.3 (2026-05-19)

### Fixed
- Made passive Codex hooks stay silent for non-`Stop` events like `PostToolUse`, while keeping `Stop` on the minimal valid JSON response and suppressing the custom `local_spans` field in Codex stdout responses

## 0.13.2 (2026-05-18)

### Added
- Added Claude Code `PreCompact` and `PostCompact` hook registration, examples, docs, and tests

### Fixed
- Suppressed passive stdout for Codex `SessionStart` and `UserPromptSubmit` while preserving JSON stdout for events like `Stop`

## 0.13.1 (2026-05-18)

### Fixed
- Updated Codex setup to use the current `[features].hooks` flag and remove deprecated `codex_hooks` entries from existing configs

## 0.13.0 (2026-05-17)

### Added
- Added a supported-agent setup matrix to the README covering Cursor, Claude Code, Gemini CLI, GitHub Copilot, OpenCode, and compatible hook runners
- Added dedicated Gemini CLI setup documentation and clarified how Gemini model, tool, and agent lifecycle events map to canonical hook spans
- Added this changelog and release workflow helpers so GitHub releases use curated release notes from `CHANGELOG.md`

### Changed
- Switched release versioning from tag-derived `setuptools-scm` metadata to a checked-in `pyproject.toml` version managed by the release workflow
- Refreshed pip/pipx, source-checkout, config, and log path docs so package installs and copied-source installs are easier to distinguish
- Updated the pinned README install example and package metadata for the `0.13.0` release

### Fixed
- Included the OpenCode TypeScript example in package data and source distributions so documented examples are present in built artifacts
