"""Privacy tests for the visible PDF signature stamp."""

from src.certificate.stamp import _mask_cpf


def test_cpf_is_masked_when_formatted() -> None:
    assert _mask_cpf("123.456.789-00") == "***.456.789-**"


def test_cpf_is_masked_when_unformatted() -> None:
    assert _mask_cpf("12345678900") == "***.456.789-**"


def test_malformed_identifier_is_not_exposed() -> None:
    assert _mask_cpf("identificador-invalido") == ""
