"""Security tests for publishing signed PDF outputs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from endesive import pdf as endesive_pdf
from reportlab.pdfgen import canvas

from src.certificate.pdf_signer import SignatureOptions, _write_validated_signed_pdf, sign_pdf


def test_validated_pdf_is_published_atomically(tmp_path, monkeypatch) -> None:
    output = tmp_path / "documento-assinado.pdf"
    original = b"%PDF-1.7\nconteudo-original\n"
    increment = b"/ByteRange [0 10 20 30]\nassinatura"
    monkeypatch.setattr(endesive_pdf, "verify", lambda _data: [(True, True, False)])

    _write_validated_signed_pdf(str(output), original, increment)

    assert output.read_bytes() == original + increment
    assert not list(tmp_path.glob(".documento-assinado.pdf.*.tmp"))


def test_invalid_signature_does_not_replace_existing_output(tmp_path, monkeypatch) -> None:
    output = tmp_path / "documento-assinado.pdf"
    output.write_bytes(b"versao-anterior")
    monkeypatch.setattr(endesive_pdf, "verify", lambda _data: [(True, False, False)])

    with pytest.raises(ValueError, match="validação criptográfica"):
        _write_validated_signed_pdf(
            str(output),
            b"%PDF-1.7\n",
            b"/ByteRange [0 1 2 3]\nassinatura-invalida",
        )

    assert output.read_bytes() == b"versao-anterior"
    assert not list(tmp_path.glob(".documento-assinado.pdf.*.tmp"))


def test_missing_new_signature_is_rejected(tmp_path, monkeypatch) -> None:
    output = tmp_path / "documento-assinado.pdf"
    monkeypatch.setattr(endesive_pdf, "verify", lambda _data: [])

    with pytest.raises(ValueError, match="não foi encontrada"):
        _write_validated_signed_pdf(
            str(output),
            b"%PDF-1.7\n",
            b"incremento-sem-assinatura",
        )

    assert not output.exists()


def test_a1_signing_produces_a_cryptographically_valid_pdf(tmp_path) -> None:
    password = "senha-de-teste"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Certificado de Teste")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    pfx_path = tmp_path / "certificado-de-teste.p12"
    pfx_path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"certificado-de-teste",
            private_key,
            certificate,
            None,
            serialization.BestAvailableEncryption(password.encode()),
        )
    )
    input_pdf = tmp_path / "documento.pdf"
    pdf = canvas.Canvas(str(input_pdf))
    pdf.drawString(72, 760, "Documento sintetico para teste automatizado")
    pdf.save()
    output_pdf = tmp_path / "documento-assinado.pdf"

    result = sign_pdf(
        str(input_pdf),
        str(pfx_path),
        password,
        str(output_pdf),
        SignatureOptions(visible=False),
    )

    assert result.success, result.error
    assert output_pdf.is_file()
    verification = endesive_pdf.verify(output_pdf.read_bytes())
    assert verification[-1][0:2] == (True, True)
