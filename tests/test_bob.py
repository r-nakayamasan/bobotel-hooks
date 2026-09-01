"""IBM Bob adapter: field mapping, stdout silence, setup, and enforcedHooks policy."""
import json
import os
import sys

import pytest
from click.testing import CliRunner

import otel_hook
from otel_hook import build_bob_enforced_hooks, cli, setup_bob


def _read(path):
    with open(path) as f:
        return json.load(f)


class RecordingSpan:
    """Minimal span stand-in that records set_attribute calls."""

    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


def _stderr(result):
    """Return a result's stderr across click versions (<8.2 mixes it into output)."""
    try:
        return result.stderr
    except ValueError:
        return result.output


# ---------------------------------------------------------------------------
# stdout must stay empty: Bob injects hook stdout into the model context for
# SessionStart and UserPromptSubmit, and has no stdout response protocol.
# ---------------------------------------------------------------------------

class TestStdoutSilence:
    @pytest.mark.parametrize("event", otel_hook._BOB_EVENTS)
    def test_no_stdout_response_for_any_bob_event(self, event):
        assert otel_hook._stdout_response(event, "bob", {"session_id": "ses_1"}) is None

    @pytest.mark.parametrize("event", otel_hook._BOB_EVENTS)
    def test_silent_even_with_governance(self, event):
        governance = otel_hook.GovernanceResponse(
            continue_=False,
            stop_reason="policy",
            system_message="blocked",
        )
        assert otel_hook._stdout_response(event, "bob", {}, governance) is None

    @pytest.mark.parametrize("event", otel_hook._BOB_EVENTS)
    def test_emit_prints_nothing(self, event, capsys):
        otel_hook._emit_stdout_response(event, "bob", {"session_id": "ses_1"})
        assert capsys.readouterr().out == ""

    def test_other_providers_still_respond(self):
        """The silence is Bob-scoped, not a global regression."""
        assert otel_hook._stdout_response("Stop", "claude", {}) == '{"continue": true}'

    @pytest.mark.parametrize("event", otel_hook._BOB_EVENTS)
    def test_end_to_end_cli_is_silent_and_exits_zero(self, event, tmp_path, monkeypatch):
        monkeypatch.setenv("IDE_OTEL_HOOK_HOME", str(tmp_path))
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        payload = json.dumps({"event": event, "session_id": "ses_01abc123"})
        result = CliRunner().invoke(cli, ["--bob"], input=payload)
        assert result.exit_code == 0
        assert result.output == "", f"{event} leaked stdout: {result.output!r}"


class TestDebugConsoleGoesToStderr:
    """IDE_OTEL_DEBUG_CONSOLE must not write spans to Bob's stdout.

    ConsoleSpanExporter defaults to sys.stdout, and Bob feeds hook stdout into
    the model context, so debug output has to be routed to stderr instead.
    """

    def test_bob_declares_stdout_model_visible(self):
        assert otel_hook._stdout_is_model_visible("bob") is True

    @pytest.mark.parametrize("ide", ["claude", "cursor", "codex", "copilot", "gemini", "opencode"])
    def test_other_providers_keep_stdout(self, ide):
        assert otel_hook._stdout_is_model_visible(ide) is False

    def test_unknown_provider_defaults_to_stdout(self):
        assert otel_hook._stdout_is_model_visible("something-new") is False
        assert otel_hook._stdout_is_model_visible(None) is False

    def test_stream_selection(self):
        assert otel_hook._debug_console_stream("bob") is sys.stderr
        assert otel_hook._debug_console_stream("claude") is sys.stdout

    def test_span_exporter_is_constructed_with_stderr(self, monkeypatch):
        """Assert the real exporter object is handed stderr, not just the helper."""
        pytest.importorskip("opentelemetry.sdk.trace")
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        monkeypatch.setattr(otel_hook, "_CONSOLE_EXPORTER_REGISTERED", False)
        provider = TracerProvider()
        monkeypatch.setattr(otel_hook.trace, "get_tracer_provider", lambda: provider)

        captured = {}
        real_init = ConsoleSpanExporter.__init__

        def spy(self, *args, **kwargs):
            captured["out"] = kwargs.get("out")
            return real_init(self, *args, **kwargs)

        monkeypatch.setattr(ConsoleSpanExporter, "__init__", spy)
        otel_hook._enable_console_exporter("bob")
        assert captured["out"] is sys.stderr

    def test_span_exporter_keeps_stdout_for_claude(self, monkeypatch):
        pytest.importorskip("opentelemetry.sdk.trace")
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        monkeypatch.setattr(otel_hook, "_CONSOLE_EXPORTER_REGISTERED", False)
        provider = TracerProvider()
        monkeypatch.setattr(otel_hook.trace, "get_tracer_provider", lambda: provider)

        captured = {}
        real_init = ConsoleSpanExporter.__init__

        def spy(self, *args, **kwargs):
            captured["out"] = kwargs.get("out")
            return real_init(self, *args, **kwargs)

        monkeypatch.setattr(ConsoleSpanExporter, "__init__", spy)
        otel_hook._enable_console_exporter("claude")
        assert captured["out"] is sys.stdout

    def test_emitted_span_json_lands_on_stderr_not_stdout(self, monkeypatch, capfd):
        """End-to-end: ending a span with the Bob console exporter writes to stderr.

        Uses capfd, not capsys: ConsoleSpanExporter binds its default ``out`` to
        sys.stdout when the class is defined, so a regression to the no-argument
        form would write past a capsys capture and the stdout assertion would
        pass for the wrong reason. capfd captures the real file descriptor.
        """
        pytest.importorskip("opentelemetry.sdk.trace")
        from opentelemetry.sdk.trace import TracerProvider

        monkeypatch.setattr(otel_hook, "_CONSOLE_EXPORTER_REGISTERED", False)
        provider = TracerProvider()
        monkeypatch.setattr(otel_hook.trace, "get_tracer_provider", lambda: provider)
        otel_hook._enable_console_exporter("bob")

        provider.get_tracer("t").start_span("gen_ai.client.hook.Stop").end()
        provider.force_flush()

        out, err = capfd.readouterr()
        assert "gen_ai.client.hook.Stop" not in out, f"span leaked to stdout: {out!r}"
        assert "gen_ai.client.hook.Stop" in err


# ---------------------------------------------------------------------------
# Tool field renames, scoped to the two tool callbacks
# ---------------------------------------------------------------------------

class TestToolFieldMapping:
    def _normalize(self, raw):
        adapter = otel_hook.BobEventAdapter()
        data = otel_hook._normalize_input_data(raw)
        return adapter.normalize(otel_hook._get_event_name(data), None, data).to_lifecycle_data()

    def test_pre_tool_use_renames_tool_and_input(self):
        data = self._normalize({
            "event": "PreToolUse",
            "session_id": "ses_1",
            "tool": "write_file",
            "input": {"path": "src/index.ts"},
        })
        assert data["tool_name"] == "write_file"
        assert data["tool_input"] == {"path": "src/index.ts"}
        assert "tool" not in data and "input" not in data

    def test_post_tool_use_renames_output(self):
        data = self._normalize({
            "event": "PostToolUse",
            "session_id": "ses_1",
            "tool": "write_file",
            "input": {"path": "src/index.ts"},
            "output": "File written successfully",
        })
        assert data["tool_output"] == "File written successfully"
        assert "output" not in data

    def test_user_prompt_submit_keeps_prompt_semantics(self):
        """`input` must not be renamed here: it is a prompt fallback key."""
        raw = {"event": "UserPromptSubmit", "session_id": "ses_1", "input": "do the thing"}
        adapter = otel_hook.BobEventAdapter()
        data = otel_hook._normalize_input_data(raw)
        event = adapter.normalize(otel_hook._get_event_name(data), None, data)
        assert [(r.kind, r.role, r.length) for r in event.conversation] == [("prompt", "user", 12)]
        assert "tool_input" not in event.to_lifecycle_data()

    def test_existing_canonical_field_is_not_overwritten(self):
        data = self._normalize({
            "event": "PreToolUse",
            "session_id": "ses_1",
            "tool": "write_file",
            "tool_name": "already_set",
        })
        assert data["tool_name"] == "already_set"

    def test_renamed_fields_reach_the_span(self):
        """The rename is only useful if the shared attribute map then picks it up."""
        data = self._normalize({
            "event": "PostToolUse",
            "session_id": "ses_1",
            "tool": "write_file",
            "input": {"path": "src/index.ts"},
            "output": "File written successfully",
        })
        span = RecordingSpan()
        for key, attr in otel_hook._EVENT_ATTR_MAP["PostToolUse"].items():
            otel_hook._set_if_present(span, attr, data.get(key))
        assert span.attributes["gen_ai.client.tool_name"] == "write_file"

    def test_mcp_encoded_tool_name_yields_mcp_identity(self):
        """The rename must precede shared MCP normalization, which reads tool_name."""
        data = self._normalize({
            "event": "PreToolUse",
            "session_id": "ses_1",
            "tool": "mcp__github__create_issue",
            "input": {"title": "x"},
        })
        assert data["tool_name"] == "mcp__github__create_issue"
        assert data["mcp_server"] == "github"
        assert data["mcp_tool"] == "create_issue"

    def test_output_is_not_recorded_as_a_shell_stream(self):
        """Bob's `output` is a tool result, not shell stdout — the rename prevents that."""
        data = self._normalize({
            "event": "PostToolUse",
            "session_id": "ses_1",
            "tool": "write_file",
            "output": "File written successfully",
        })
        assert "output" not in data
        assert data["tool_output"] == "File written successfully"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class TestDetection:
    def test_cli_flag_wins(self, monkeypatch):
        monkeypatch.setattr(otel_hook, "_CLI_HOOK_SOURCE", "bob")
        assert otel_hook._detect_ide({"event": "Stop", "session_id": "ses_1"}) == "bob"

    @pytest.mark.parametrize("name", ["bob", "Bob", "IBM Bob", "bob cli", "bob ide"])
    def test_name_normalization(self, name):
        assert otel_hook._normalize_ide_name(name) == "bob"

    def test_payload_heuristic(self, monkeypatch):
        monkeypatch.setattr(otel_hook, "_CLI_HOOK_SOURCE", None)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.setattr(otel_hook, "_detect_ide_from_process_tree", lambda: None)
        assert otel_hook._detect_ide({"event": "PreToolUse", "session_id": "ses_1"}) == "bob"

    def test_heuristic_does_not_shadow_claude_payloads(self, monkeypatch):
        monkeypatch.setattr(otel_hook, "_CLI_HOOK_SOURCE", None)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.setattr(otel_hook, "_detect_ide_from_process_tree", lambda: None)
        data = {"hook_event_name": "PreToolUse", "event": "PreToolUse", "session_id": "ses_1"}
        assert otel_hook._detect_ide(data) != "bob"

    def test_adapter_lookup(self):
        assert otel_hook._event_adapter_for("bob").provider == "bob"


# ---------------------------------------------------------------------------
# setup_bob
# ---------------------------------------------------------------------------

class TestSetupBob:
    def test_creates_project_settings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(otel_hook, "_resolve_hook_cmd", lambda: "otel-hook")
        setup_bob(global_=False, cwd=str(tmp_path))
        path = tmp_path / ".bob" / "settings.json"
        assert path.exists()
        hooks = _read(str(path))["hooks"]
        assert sorted(hooks) == sorted(otel_hook._BOB_EVENTS)
        assert hooks["SessionStart"] == [
            {"hooks": [{
                "type": "command",
                "command": "otel-hook --bob",
                "timeout": otel_hook._BOB_HOOK_TIMEOUT_SECONDS,
            }]}
        ]

    def test_matcher_only_on_tool_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr(otel_hook, "_resolve_hook_cmd", lambda: "otel-hook")
        setup_bob(global_=False, cwd=str(tmp_path))
        hooks = _read(str(tmp_path / ".bob" / "settings.json"))["hooks"]
        for event, entries in hooks.items():
            has_matcher = "matcher" in entries[0]
            assert has_matcher == (event in otel_hook._BOB_MATCHER_EVENTS), event

    def test_global_path_has_extra_settings_level(self):
        expected = os.path.join(os.path.expanduser("~"), ".bob", "settings", "settings.json")
        assert otel_hook._bob_settings_path(True, ".") == expected

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(otel_hook, "_resolve_hook_cmd", lambda: "otel-hook")
        setup_bob(global_=False, cwd=str(tmp_path))
        before = _read(str(tmp_path / ".bob" / "settings.json"))
        setup_bob(global_=False, cwd=str(tmp_path))
        assert _read(str(tmp_path / ".bob" / "settings.json")) == before

    def test_preserves_unrelated_hooks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(otel_hook, "_resolve_hook_cmd", lambda: "otel-hook")
        path = tmp_path / ".bob" / "settings.json"
        os.makedirs(str(path.parent))
        with open(path, "w") as f:
            json.dump({"hooks": {"PreToolUse": [
                {"matcher": "^write_file$", "hooks": [{"type": "command", "command": "sh .bob/hooks/check.sh"}]}
            ]}}, f)
        setup_bob(global_=False, cwd=str(tmp_path))
        entries = _read(str(path))["hooks"]["PreToolUse"]
        commands = [h["command"] for entry in entries for h in entry["hooks"]]
        assert "sh .bob/hooks/check.sh" in commands
        assert "otel-hook --bob" in commands

    def test_uninstall_removes_only_our_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(otel_hook, "_resolve_hook_cmd", lambda: "otel-hook")
        setup_bob(global_=False, cwd=str(tmp_path))
        result = CliRunner().invoke(
            cli, ["uninstall", "--agent", "bob", "--no-global", "--cwd", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert _read(str(tmp_path / ".bob" / "settings.json")).get("hooks", {}) == {}

    def test_registered_in_cli_surfaces(self):
        assert "bob" in otel_hook._SUPPORTED_AGENTS
        assert "bob" in otel_hook._agent_config_paths(False, ".")


# ---------------------------------------------------------------------------
# enforcedHooks group policy
# ---------------------------------------------------------------------------

class TestEnforcedHooksPolicy:
    def test_covers_every_bob_event(self):
        policy = build_bob_enforced_hooks(hook_cmd="/opt/otel-hook/bin/otel-hook")
        assert sorted(policy) == sorted(otel_hook._BOB_EVENTS)
        for event, entries in policy.items():
            hook = entries[0]["hooks"][0]
            assert hook["type"] == "command"
            assert hook["command"] == "/opt/otel-hook/bin/otel-hook --bob"
            assert hook["timeout"] == otel_hook._BOB_HOOK_TIMEOUT_SECONDS
            assert ("matcher" in entries[0]) == (event in otel_hook._BOB_MATCHER_EVENTS)

    def test_portable_uses_bare_command(self):
        policy = build_bob_enforced_hooks(portable=True)
        assert policy["Stop"][0]["hooks"][0]["command"] == "otel-hook --bob"

    def test_zero_timeout_is_omitted(self):
        policy = build_bob_enforced_hooks(hook_cmd="/opt/otel-hook", timeout=0)
        assert "timeout" not in policy["Stop"][0]["hooks"][0]

    def test_raw_is_single_encoded_paste_ready_json(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--hook-cmd", "/opt/otel-hook/bin/otel-hook", "--raw"]
        )
        assert result.exit_code == 0
        line = result.stdout.strip()
        assert "\n" not in line
        assert json.loads(line) == build_bob_enforced_hooks(hook_cmd="/opt/otel-hook/bin/otel-hook")

    def test_escaped_round_trips_through_two_decodes(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--hook-cmd", "/opt/otel-hook/bin/otel-hook", "--escaped"]
        )
        assert result.exit_code == 0
        decoded = json.loads(json.loads(result.stdout.strip()))
        assert decoded == build_bob_enforced_hooks(hook_cmd="/opt/otel-hook/bin/otel-hook")

    def test_default_output_is_pretty_and_valid(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--hook-cmd", "/opt/otel-hook/bin/otel-hook"]
        )
        assert result.exit_code == 0
        assert "\n" in result.stdout.strip()
        assert json.loads(result.stdout)["PreToolUse"][0]["matcher"] == ".*"

    def test_absolute_hook_cmd_emits_no_warning(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--hook-cmd", "/opt/otel-hook/bin/otel-hook"]
        )
        assert result.exit_code == 0
        assert "Warning" not in _stderr(result)

    def test_portable_warns_about_silent_data_loss(self):
        result = CliRunner().invoke(cli, ["policy", "--bob", "--portable"])
        assert result.exit_code == 0
        assert "PATH" in _stderr(result)
        assert "silently" in _stderr(result)

    def test_bare_policy_requires_an_agent_flag(self):
        result = CliRunner().invoke(cli, ["policy"])
        assert result.exit_code != 0
        assert "--bob" in result.output

    def test_negative_timeout_is_rejected(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--hook-cmd", "/opt/otel-hook", "--timeout", "-5"]
        )
        assert result.exit_code != 0
        assert "--timeout" in result.output

    def test_hook_cmd_and_portable_conflict(self):
        result = CliRunner().invoke(
            cli, ["policy", "--bob", "--portable", "--hook-cmd", "/opt/otel-hook"]
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_matches_bob_config_schema_shape(self):
        """Every entry must be {matcher?, hooks:[{type,command,timeout?}]} as Bob documents."""
        policy = build_bob_enforced_hooks(hook_cmd="/opt/otel-hook")
        for entries in policy.values():
            assert isinstance(entries, list)
            for entry in entries:
                assert set(entry) <= {"matcher", "hooks"}
                for hook in entry["hooks"]:
                    assert set(hook) <= {"type", "command", "timeout"}
