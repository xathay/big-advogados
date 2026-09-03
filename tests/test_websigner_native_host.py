"""Testes do protocolo Native Messaging usado pelo Web Signer."""

from __future__ import annotations

import stat
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from src.websigner import installer as websigner_installer
from src.websigner import native_host


def test_authorize_certificate_access_allows_and_remembers(monkeypatch) -> None:
    replies: list[tuple[str, object]] = []
    seen_domains: list[str] = []

    monkeypatch.setattr(
        native_host,
        "_ask_certificate_access",
        lambda domain: seen_domains.append(domain) or True,
    )
    monkeypatch.setattr(
        native_host,
        "reply_success",
        lambda request_id, response: replies.append((request_id, response)),
    )

    native_host.handle_command({
        "requestId": "request-1",
        "command": "authorizeCertificateAccess",
        "domain": "esaj.tjsp.jus.br",
        "request": {},
    })

    assert seen_domains == ["esaj.tjsp.jus.br"]
    assert replies == [("request-1", {"authorized": True, "dontAskAgain": True})]


def test_authorize_certificate_access_preserves_denial(monkeypatch) -> None:
    replies: list[tuple[str, object]] = []

    monkeypatch.setattr(native_host, "_ask_certificate_access", lambda _domain: False)
    monkeypatch.setattr(
        native_host,
        "reply_success",
        lambda request_id, response: replies.append((request_id, response)),
    )

    native_host.handle_command({
        "requestId": "request-2",
        "command": "authorizeCertificateAccess",
        "domain": "esaj.tjsp.jus.br",
    })

    assert replies == [("request-2", {"authorized": False, "dontAskAgain": False})]


def test_certificate_access_dialog_sanitizes_domain(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr(native_host.subprocess, "run", fake_run)

    assert native_host._ask_certificate_access("esaj.tjsp.jus.br\ntexto-injetado") is True
    assert len(commands) == 1
    assert "texto-injetado" not in " ".join(commands[0])


def test_signature_authorization_requires_explicit_consent(monkeypatch) -> None:
    native_host._signature_grants.clear()
    replies: list[tuple[str, object]] = []
    prompts: list[tuple[str, str, str]] = []
    cert = {
        "thumbprint": "abc123",
        "subjectName": "CN=Titular do certificado",
        "issuerName": "CN=Autoridade Certificadora",
    }

    monkeypatch.setattr(native_host, "list_certificates_from_nss", lambda: [cert])
    monkeypatch.setattr(native_host, "list_certificates_from_a3", lambda: [])
    monkeypatch.setattr(
        native_host,
        "_ask_signature_authorization",
        lambda domain, _cert, command, _request: prompts.append(
            (domain, _cert["thumbprint"], command),
        ) or True,
    )
    monkeypatch.setattr(
        native_host,
        "reply_success",
        lambda request_id, response: replies.append((request_id, response)),
    )

    native_host.handle_command({
        "requestId": "signature-request",
        "command": "authorizeSignatures",
        "domain": "esaj.tjsp.jus.br",
        "request": {"certificateThumbprint": "abc123"},
    })

    assert prompts == [("esaj.tjsp.jus.br", "abc123", "authorizeSignatures")]
    assert replies == [(
        "signature-request",
        {
            "authorized": True,
            "dontAskAgain": False,
            "certificate": cert,
        },
    )]
    assert native_host._signature_grants == {("esaj.tjsp.jus.br", "abc123"): 1}
    native_host._signature_grants.clear()


def test_signature_authorization_dialog_sanitizes_display_values(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return CompletedProcess(cmd, 1)

    monkeypatch.setattr(native_host.subprocess, "run", fake_run)

    allowed = native_host._ask_signature_authorization(
        "esaj.tjsp.jus.br\ndomínio-injetado",
        {"subjectName": "CN=Titular\ntexto-injetado"},
        "authorizeSignatures",
        {},
    )

    assert allowed is False
    rendered = " ".join(commands[0])
    assert "domínio-injetado" not in rendered
    assert "texto-injetado" not in rendered


def test_save_config_is_owner_only_and_atomic(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_file = config_dir / "websigner.json"
    monkeypatch.setattr(native_host, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(native_host, "CONFIG_FILE", config_file)

    native_host.save_config({"pfx_path": "/caminho/local/certificado.pfx"})

    assert config_file.is_file()
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert not list(config_dir.glob(".websigner-*"))


def test_sign_hash_is_rejected_without_ephemeral_grant(monkeypatch) -> None:
    errors: list[tuple[str, str, str]] = []
    native_host._signature_grants.clear()
    monkeypatch.setattr(
        native_host,
        "reply_error",
        lambda request_id, message, code: errors.append((request_id, message, code)),
    )
    monkeypatch.setattr(
        native_host,
        "sign_hash",
        lambda *_args: pytest.fail("private key must not be used without authorization"),
    )

    native_host.handle_command({
        "requestId": "sign-without-grant",
        "command": "signHash",
        "domain": "esaj.tjsp.jus.br",
        "request": {
            "certificateThumbprint": "abc123",
            "hash": "hash-em-base64",
            "digestAlgorithm": "sha256",
        },
    })

    assert errors == [(
        "sign-without-grant",
        "Signature operation was not authorized",
        "signature_not_authorized",
    )]


def test_signature_grant_is_consumed_once(monkeypatch) -> None:
    replies: list[tuple[str, object]] = []
    errors: list[tuple[str, str, str]] = []
    native_host._signature_grants.clear()
    assert native_host._grant_signatures("esaj.tjsp.jus.br", "abc123", 1)
    monkeypatch.setattr(native_host, "sign_hash", lambda *_args: "assinatura-base64")
    monkeypatch.setattr(
        native_host,
        "reply_success",
        lambda request_id, response: replies.append((request_id, response)),
    )
    monkeypatch.setattr(
        native_host,
        "reply_error",
        lambda request_id, message, code: errors.append((request_id, message, code)),
    )
    message = {
        "requestId": "primeira",
        "command": "signHash",
        "domain": "esaj.tjsp.jus.br",
        "request": {
            "certificateThumbprint": "abc123",
            "hash": "hash-em-base64",
            "digestAlgorithm": "sha256",
        },
    }

    native_host.handle_command(message)
    message["requestId"] = "segunda"
    native_host.handle_command(message)

    assert replies == [("primeira", "assinatura-base64")]
    assert errors[-1][0::2] == ("segunda", "signature_not_authorized")


def test_batch_grant_matches_batch_size_and_response_contract(monkeypatch) -> None:
    replies: list[tuple[str, object]] = []
    native_host._signature_grants.clear()
    assert native_host._grant_signatures("esaj.tjsp.jus.br", "abc123", 2)
    monkeypatch.setattr(native_host, "sign_hash", lambda _thumb, value, _alg: f"sig-{value}")
    monkeypatch.setattr(
        native_host,
        "reply_success",
        lambda request_id, response: replies.append((request_id, response)),
    )

    native_host.handle_command({
        "requestId": "lote",
        "command": "signHashBatch",
        "domain": "esaj.tjsp.jus.br",
        "request": {
            "certificateThumbprint": "abc123",
            "digestAlgorithm": "sha256",
            "batch": [{"hash": "um"}, {"hash": "dois"}],
        },
    })

    assert replies == [("lote", {"signatures": ["sig-um", "sig-dois"]})]
    assert native_host._signature_grants == {}


def test_unknown_command_uses_extension_compatibility_code(monkeypatch) -> None:
    errors: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        native_host,
        "reply_error",
        lambda request_id, message, code: errors.append((request_id, message, code)),
    )

    native_host.handle_command({"requestId": "request-3", "command": "futureCommand"})

    assert errors == [("request-3", "Unknown command: futureCommand", "command_unknown")]


def test_native_wrapper_does_not_follow_mise_or_pyenv_path(tmp_path, monkeypatch) -> None:
    native_host_script = tmp_path / "native_host.py"
    native_host_script.write_text("# test host\n")
    wrapper_dir = tmp_path / "wrapper"

    monkeypatch.setattr(
        websigner_installer,
        "_find_native_host_script",
        lambda: str(native_host_script),
    )

    wrapper = websigner_installer._create_wrapper_script(wrapper_dir)
    content = Path(wrapper).read_text()

    assert 'exec "/usr/bin/python3"' in content
    assert "exec python3 " not in content
