import os
import tempfile
from unittest.mock import MagicMock, patch

from google.genai import errors as genai_errors

from main import (
    MODEL_NAMES,
    _load_pdf,
    extract_data,
    load_file,
    parse_json,
    process_file,
    process_folder,
)


def test_load_file_empty_returns_none():
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        assert load_file(path) is None
    finally:
        os.remove(path)


def test_scanned_invoice_regression():
    pdf_path = "test-files/scanned-invoice-test.pdf"
    assert os.path.exists(pdf_path), f"Required test file missing: {pdf_path}"
    assert os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY not set in environment"

    result = process_file(pdf_path, schema="invoice")

    assert result is not None
    assert result["invoice_number"] == "MOS-2026-00417"
    assert result["vendor_name"] == "Meridian Office Supplies Co."
    assert result["total_amount"] == 701.71
    assert len(result["line_items"]) == 5


def test_process_folder_mixed_types():
    fixed_json = (
        '{"invoice_number":"INV-1","vendor_name":"Acme",'
        '"customer_name":null,"customer_email":null,'
        '"total_amount":10.0,"order_date":null,"due_date":null,'
        '"line_items":[]}'
    )
    with tempfile.TemporaryDirectory() as folder:
        txt_path = os.path.join(folder, "invoice1.txt")
        with open(txt_path, "w") as f:
            f.write("Some plain-text invoice content.")

        pdf_path = os.path.join(folder, "invoice2.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 not a real pdf, just non-empty bytes")

        with patch("main.extract_data", return_value=fixed_json):
            results = process_folder(folder, schema="invoice")

    assert "invoice1.txt" in results
    assert "invoice2.pdf" in results


def test_parse_json_invalid_returns_none():
    assert parse_json("not valid json") is None


def test_process_folder_uppercase_extension():
    fixed_json = (
        '{"invoice_number":"INV-1","vendor_name":"Acme",'
        '"customer_name":null,"customer_email":null,'
        '"total_amount":10.0,"order_date":null,"due_date":null,'
        '"line_items":[]}'
    )
    with tempfile.TemporaryDirectory() as folder:
        pdf_path = os.path.join(folder, "Invoice.PDF")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 not a real pdf, just non-empty bytes")

        with patch("main.extract_data", return_value=fixed_json):
            results = process_folder(folder, schema="invoice")

    assert "Invoice.PDF" in results


def test_extract_data_missing_api_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # No client should even be constructed once the key check fails, but
    # patch it anyway so a regression that skips the early return can't
    # slip through by making a real network call.
    with patch("main.genai.Client") as mock_client_cls:
        result = extract_data("some invoice text", schema="invoice")

    assert result is None
    mock_client_cls.assert_not_called()


def test_extract_data_invalid_schema_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    # get_extract_prompt() raises ValueError before any client is built, so
    # this also should never reach the network — patched for the same
    # regression-proofing reason as above.
    with patch("main.genai.Client") as mock_client_cls:
        result = extract_data("some invoice text", schema="not_a_real_schema")

    assert result is None
    mock_client_cls.assert_not_called()


def test_process_folder_nonexistent_dir_returns_none():
    assert process_folder("/no/such/directory/at/all", schema="invoice") is None


def test_process_folder_empty_dir_returns_none():
    with tempfile.TemporaryDirectory() as folder:
        assert process_folder(folder, schema="invoice") is None


def test_load_pdf_corrupt_falls_back_to_native():
    garbage = b"this is not a real pdf, just garbage bytes for pypdf to choke on"

    result = _load_pdf("garbage.pdf", garbage)

    assert result is not None
    text, pdf_bytes = result
    assert text == ""
    assert pdf_bytes == garbage


def test_extract_data_model_fallback_on_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    rate_limit_error = genai_errors.ClientError(429, {"message": "Rate limit exceeded"})
    success_response = MagicMock(text='{"invoice_number":"INV-1"}')

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [rate_limit_error, success_response]

    with patch("main.genai.Client", return_value=mock_client):
        result = extract_data("some invoice text", schema="invoice")

    assert result == '{"invoice_number":"INV-1"}'
    assert mock_client.models.generate_content.call_count == 2
    first_model = mock_client.models.generate_content.call_args_list[0].kwargs["model"]
    second_model = mock_client.models.generate_content.call_args_list[1].kwargs["model"]
    assert first_model == MODEL_NAMES[0]
    assert second_model == MODEL_NAMES[1]
