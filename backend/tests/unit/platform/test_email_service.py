"""Email package: factory selection, console logging, Resend client."""

import httpx
import pytest

from app.core.config import settings
from app.email import (
    ConsoleEmailClient,
    ResendEmailClient,
    _reset_default_email_client,
    get_default_email_client,
)
from app.email.exceptions import EmailAuthError, EmailSendError
from app.email.resend_client import RESEND_API_URL
from app.email.templates import otp_email
from app.modules.auth.models import OtpPurpose


@pytest.fixture(autouse=True)
def reset_factory():
    _reset_default_email_client()
    yield
    _reset_default_email_client()


class TestFactory:
    def test_default_is_console(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
        assert isinstance(get_default_email_client(), ConsoleEmailClient)

    def test_resend_selected_when_key_present(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        assert isinstance(get_default_email_client(), ResendEmailClient)

    def test_resend_without_key_falls_back_to_console(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
        monkeypatch.setattr(settings, "RESEND_API_KEY", "")
        assert isinstance(get_default_email_client(), ConsoleEmailClient)

    def test_unknown_provider_falls_back_to_console(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "ses")
        assert isinstance(get_default_email_client(), ConsoleEmailClient)

    def test_singleton_cached(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
        assert get_default_email_client() is get_default_email_client()


class TestConsoleClient:
    def test_logs_message(self, caplog):
        client = ConsoleEmailClient()
        with caplog.at_level("INFO", logger="app.email.console_client"):
            client.send(to="a@b.com", subject="Hi", html="<p>123456</p>", text="123456")
        assert "a@b.com" in caplog.text
        assert "123456" in caplog.text


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class TestResendClient:
    def _capture_post(self, monkeypatch, response):
        calls = {}

        def fake_post(url, *, json, headers, timeout):
            calls["url"] = url
            calls["json"] = json
            calls["headers"] = headers
            return response

        monkeypatch.setattr(httpx, "post", fake_post)
        return calls

    def test_sends_expected_request(self, monkeypatch):
        calls = self._capture_post(monkeypatch, _FakeResponse(200))
        client = ResendEmailClient(api_key="re_k", from_address="X <x@resend.dev>")
        client.send(to="u@e.com", subject="S", html="<b>h</b>", text="t")

        assert calls["url"] == RESEND_API_URL
        assert calls["headers"]["Authorization"] == "Bearer re_k"
        assert calls["json"] == {
            "from": "X <x@resend.dev>",
            "to": ["u@e.com"],
            "subject": "S",
            "html": "<b>h</b>",
            "text": "t",
        }

    def test_non_2xx_raises_send_error(self, monkeypatch):
        self._capture_post(monkeypatch, _FakeResponse(422, "bad"))
        client = ResendEmailClient(api_key="re_k")
        with pytest.raises(EmailSendError):
            client.send(to="u@e.com", subject="S", html="h")

    def test_401_raises_auth_error(self, monkeypatch):
        self._capture_post(monkeypatch, _FakeResponse(401))
        client = ResendEmailClient(api_key="re_bad")
        with pytest.raises(EmailAuthError):
            client.send(to="u@e.com", subject="S", html="h")

    def test_network_error_raises_send_error(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("no network")

        monkeypatch.setattr(httpx, "post", boom)
        client = ResendEmailClient(api_key="re_k")
        with pytest.raises(EmailSendError):
            client.send(to="u@e.com", subject="S", html="h")


class TestTemplates:
    def test_otp_email_contains_code_and_ttl(self):
        subject, html, text = otp_email(
            code="987654", purpose=OtpPurpose.REGISTRATION, ttl_minutes=10
        )
        assert "Verify" in subject
        assert "987654" in html and "987654" in text
        assert "10 minutes" in text

    def test_reset_purpose_has_distinct_subject(self):
        subject, _, _ = otp_email(
            code="111111", purpose=OtpPurpose.PASSWORD_RESET, ttl_minutes=10
        )
        assert "Reset" in subject
