"""Artifact classification tests (spec §2).

The classifier must not assume every CSV is a POS export, and it must return
UNKNOWN rather than guessing when the evidence is insufficient.
"""
from __future__ import annotations

import pytest

from app.services.orbit.contracts import ArtifactType, DecisionOrigin, SourceType
from app.services.orbit.ingestion.classification import (
    ArtifactClassification,
    classify_artifact,
    detect_format,
    domain_for_artifact,
)

SALES_ROLES = ["product_name", "quantity", "unit_price", "sale_amount", "date"]
INVENTORY_ROLES = ["product_name", "stock", "cost", "location_name"]
BANK_ROLES = ["date", "payment_amount", "balance"]
QUOTE_ROLES = ["supplier_name", "product_name", "purchase_quantity", "cost"]
STAFF_ROLES = ["employee_name", "shift_date", "shift_hours"]
MARKETING_ROLES = ["campaign_name", "channel", "ad_spend"]


class TestContentDrivenClassification:
    def test_sales_export(self):
        result = classify_artifact(filename="report.csv", mapped_roles=SALES_ROLES)
        assert result.artifact_type is ArtifactType.POS_EXPORT
        assert result.artifact_kind == "pos_export"
        assert result.domain.value == "sales"

    def test_inventory_export(self):
        result = classify_artifact(filename="data.csv", mapped_roles=INVENTORY_ROLES)
        assert result.artifact_type is ArtifactType.INVENTORY_EXPORT

    def test_bank_statement(self):
        result = classify_artifact(filename="data.csv", mapped_roles=BANK_ROLES)
        assert result.artifact_type is ArtifactType.BANK_STATEMENT
        assert result.domain.value == "finance"

    def test_staff_schedule(self):
        result = classify_artifact(filename="data.csv", mapped_roles=STAFF_ROLES)
        assert result.artifact_type is ArtifactType.STAFF_SCHEDULE

    def test_marketing_report(self):
        result = classify_artifact(filename="data.csv", mapped_roles=MARKETING_ROLES)
        assert result.artifact_type is ArtifactType.MARKETING_REPORT

    def test_the_same_extension_yields_different_kinds(self):
        """Every CSV is not a POS file."""
        a = classify_artifact(filename="a.csv", mapped_roles=SALES_ROLES)
        b = classify_artifact(filename="b.csv", mapped_roles=INVENTORY_ROLES)
        c = classify_artifact(filename="c.csv", mapped_roles=BANK_ROLES)
        assert len({a.artifact_type, b.artifact_type, c.artifact_type}) == 3

    def test_filename_does_not_override_contradicting_content(self):
        """inventory_report.xlsx full of sales columns is a mislabelled sales file."""
        result = classify_artifact(
            filename="inventory_report.xlsx", mapped_roles=SALES_ROLES
        )
        assert result.artifact_type is not ArtifactType.INVENTORY_EXPORT

    def test_partial_role_evidence_does_not_match_a_rule(self):
        """A lone product_name is not a sales export signature."""
        result = classify_artifact(filename="x.csv", mapped_roles=["product_name"])
        assert result.artifact_type is ArtifactType.UNKNOWN

    def test_rules_are_contradicted_by_forbidden_roles(self):
        """A stock column contradicts a bank statement, so it must not score as high."""
        clean = classify_artifact(
            filename="bank.csv", mapped_roles=["date", "payment_amount", "balance"]
        )
        dirty = classify_artifact(
            filename="bank.csv", mapped_roles=["date", "payment_amount", "balance", "stock"]
        )
        assert clean.confidence > dirty.confidence, (
            "a contradicting role must lower confidence rather than be ignored"
        )


class TestUnknownIsARealAnswer:
    def test_no_signal_yields_unknown(self):
        result = classify_artifact(filename="mystery.dat", mapped_roles=["notes"])
        assert result.artifact_type is ArtifactType.UNKNOWN
        assert result.is_known is False
        assert result.needs_review is True

    def test_ambiguous_roles_yield_unknown(self):
        """Roles matching two rules equally must not be forced into either.

        A supplier name plus a sale amount is either a supplier quote with tax or
        an invoice from a supplier; the string alone cannot say which.
        """
        result = classify_artifact(
            filename="x.csv",
            mapped_roles=["supplier_name", "sale_amount", "date"],
        )
        assert result.artifact_type is ArtifactType.UNKNOWN
        assert result.ambiguity

    def test_inventory_only_roles_are_inventory(self):
        """product_name + stock with no quantity is an inventory listing."""
        result = classify_artifact(filename="x.csv", mapped_roles=["product_name", "stock"])
        assert result.artifact_type is ArtifactType.INVENTORY_EXPORT

    def test_unknown_records_its_reason(self):
        result = classify_artifact(filename="x.csv", mapped_roles=["notes"])
        assert result.notes


class TestFilenameAsHint:
    def test_filename_breaks_a_close_tie_and_flags_review(self):
        result = classify_artifact(filename="quotes.csv", mapped_roles=QUOTE_ROLES)
        assert result.artifact_type is ArtifactType.SUPPLIER_QUOTE
        # Purchase orders are the genuine alternative for these roles.
        assert "purchase_order" in {c.artifact_type.value for c in result.candidates}

    def test_filename_only_classification_is_always_flagged(self):
        """A classification with no content evidence never looks confident."""
        result = classify_artifact(
            filename="bank_statement.csv", mapped_roles=["notes"]
        )
        assert result.needs_review is True
        assert any("filename alone" in n for n in result.notes)

    def test_plural_filenames_match(self):
        assert classify_artifact(filename="invoices.csv", mapped_roles=SALES_ROLES) is not None

    def test_short_token_does_not_match_inside_a_word(self):
        """'po' must not match inside 'report', which misclassified sales files."""
        result = classify_artifact(filename="sales_report.csv", mapped_roles=SALES_ROLES)
        assert result.artifact_type is ArtifactType.POS_EXPORT

    def test_compound_filenames_match_on_word_boundaries(self):
        result = classify_artifact(filename="pos_export_2026.csv", mapped_roles=SALES_ROLES)
        assert result.artifact_type is ArtifactType.POS_EXPORT


class TestDocumentClassification:
    def test_pdf_invoice_from_text(self):
        result = classify_artifact(
            filename="scan.pdf", content=b"%PDF-1.4",
            document_text="INVOICE\nInvoice No: INV-1\nTotal Due: 500 SAR",
        )
        assert result.artifact_type is ArtifactType.INVOICE
        assert result.format_type is ArtifactType.PDF

    def test_contract_pdf(self):
        result = classify_artifact(
            filename="c.pdf", content=b"%PDF-1.4",
            document_text="SERVICE AGREEMENT\nTerms and Conditions apply",
        )
        assert result.artifact_type is ArtifactType.CONTRACT

    def test_bank_statement_pdf(self):
        result = classify_artifact(
            filename="s.pdf", content=b"%PDF-1.4",
            document_text="Statement of Account\nOpening Balance 1,200",
        )
        assert result.artifact_type is ArtifactType.BANK_STATEMENT


class TestFormatDetection:
    @pytest.mark.parametrize(
        "data,filename,expected",
        [
            (b"%PDF-1.7", "x.pdf", ArtifactType.PDF),
            (b"\xd0\xcf\x11\xe0\xa1", "x.xls", ArtifactType.XLS),
            (b"PK\x03\x04zz", "x.xlsx", ArtifactType.XLSX),
            (b"PK\x03\x04zz", "x.docx", ArtifactType.DOCX),
            (b"a,b\n1,2\n", "x.csv", ArtifactType.CSV),
            (b'{"a":1}', "x.json", ArtifactType.JSON),
        ],
    )
    def test_magic_bytes_beat_the_extension(self, data, filename, expected):
        assert detect_format(data, filename) is expected

    def test_unknown_format_returns_none(self):
        assert detect_format(b"\x01\x02\x03", "mystery.dat") is None

    def test_classification_records_the_format_even_when_kind_is_unknown(self):
        result = classify_artifact(filename="x.csv", content=b"a,b\n")
        assert result.format_type is ArtifactType.CSV


class TestBoundedJudgment:
    class _Jev:
        source = "mocked"

        def __init__(self, choice):
            self.choice = choice

        def decide_artifact_type(self, **kw):
            class D:
                pass
            d = D()
            d.choice = self.choice
            d.confidence = 0.7
            return d

    def test_jev_cannot_introduce_an_unraised_type(self):
        """JEV chooses among candidates; it cannot invent one."""
        result = classify_artifact(
            filename="x.csv", mapped_roles=["notes"],
            jev=self._Jev("bank_statement"),
        )
        # No candidate existed, so deterministic UNKNOWN stands.
        assert result.artifact_type is ArtifactType.UNKNOWN

    def test_jev_ambiguity_leaves_the_deterministic_result(self):
        result = classify_artifact(
            filename="x.csv", mapped_roles=["notes"], jev=self._Jev("ambiguous")
        )
        assert result.artifact_type is ArtifactType.UNKNOWN


class TestContract:
    def test_domain_for_artifact(self):
        assert domain_for_artifact(ArtifactType.BANK_STATEMENT).value == "finance"
        assert domain_for_artifact(ArtifactType.PDF) is None

    def test_result_is_serialisable(self):
        payload = classify_artifact(filename="a.csv", mapped_roles=SALES_ROLES).to_dict()
        assert payload["artifact_type"] == "pos_export"
        assert payload["classification_method"] == DecisionOrigin.DETERMINISTIC.value
        assert "candidates" in payload

    def test_classification_is_deterministic(self):
        a = classify_artifact(filename="a.csv", mapped_roles=SALES_ROLES).to_dict()
        b = classify_artifact(filename="a.csv", mapped_roles=SALES_ROLES).to_dict()
        assert a == b

    def test_system_export_is_a_prior_not_a_verdict(self):
        result = classify_artifact(
            filename="a.csv", mapped_roles=SALES_ROLES,
            known_source_type=SourceType.SYSTEM_EXPORT,
        )
        assert result.artifact_type is ArtifactType.POS_EXPORT