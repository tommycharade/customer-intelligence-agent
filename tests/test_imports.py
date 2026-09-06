import pytest

from customer_intelligence.imports import preview


def test_csv_import_records_explicit_exclusions():
    source = preview(
        "accounts.csv", b"company,domain,exclude,notes\nCompany,company.com,true,Existing customer\n"
    )[0]
    assert source.source_type == "exclusion"
    assert source.account_domain == "company.com"


def test_eml_preview_exposes_association_for_correction():
    source = preview(
        "enquiry.eml",
        b"From: Person <person@company.com>\nSubject: Ownership checks\nContent-Type: text/plain\n\nWe compare service ownership manually.\n",
    )[0]
    assert source.account_domain == "company.com"
    assert "We compare" in source.text
    assert source.source_type == "inbound"


@pytest.mark.parametrize(
    "filename,content",
    [("empty.txt", b""), ("unknown.exe", b"content"), ("large.txt", b"a" * (10 * 1024 * 1024 + 1))],
)
def test_invalid_or_large_imports_are_rejected(filename, content):
    with pytest.raises(ValueError):
        preview(filename, content)
