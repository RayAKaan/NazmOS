"""Stage 3: universal vocabulary, column mapper and row roles.

The repository previously carried five mutually incompatible column
vocabularies and three date parsers. These tests pin the single authority that
replaces them, with emphasis on the failure modes that produce wrong numbers:

* an ambiguous money header must not be silently resolved;
* a TOTAL row must never become a transaction;
* "subtotal" must not be reported as a grand total;
* an unmatched header must stay unmapped rather than coerced to the nearest role.
"""
from __future__ import annotations

import pytest

from app.services.orbit.contracts import RowRole
from app.services.orbit.semantics import (
    ALL_ROLES,
    CURRENCY_ROLES,
    ColumnMappingStatus,
    SemanticRole,
    UnitDimension,
    ValueType,
    classify_rows,
    domain_of,
    get_role,
    map_columns,
    unit_dimension_of,
    validate_vocabulary,
)
from app.services.orbit.semantics.column_mapper import parse_numeric
from app.services.orbit.semantics.vocabulary import (
    GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND,
    ROLES_BY_ARTIFACT_KIND,
    designated_role_for,
    roles_for_domain,
)
from app.services.orbit.contracts import DomainCapability


# ── vocabulary integrity ────────────────────────────────────────────────────

class TestVocabulary:
    def test_vocabulary_is_internally_consistent(self):
        """No alias may be claimed by two specific roles.

        A collision here would be resolved by dict ordering, i.e. arbitrarily,
        which is how the old alias tables produced inconsistent mappings.
        """
        assert validate_vocabulary() == []

    def test_every_role_declares_a_domain(self):
        for role in ALL_ROLES:
            assert isinstance(role.domain, DomainCapability), role.canonical_name

    def test_currency_roles_are_currency_typed(self):
        for name in CURRENCY_ROLES:
            role = get_role(name)
            assert role.value_type is ValueType.CURRENCY, name
            assert unit_dimension_of(name) is UnitDimension.CURRENCY

    def test_quantity_roles_have_a_unit_dimension(self):
        for role in ALL_ROLES:
            if role.value_type is ValueType.QUANTITY:
                assert role.unit_dimension is not None, role.canonical_name

    def test_all_required_domains_are_covered(self):
        for domain in DomainCapability:
            assert roles_for_domain(domain), f"no roles for domain {domain.value}"

    def test_identity_roles_cover_products_and_suppliers(self):
        assert domain_of("product_name") is DomainCapability.SALES
        assert domain_of("supplier_name") is DomainCapability.PROCUREMENT
        assert domain_of("customer_name") is DomainCapability.CUSTOMER
        assert domain_of("employee_name") is DomainCapability.WORKFORCE

    def test_sales_and_purchase_money_are_distinct_roles(self):
        """Collapsing these is how fictional margins appeared."""
        assert "sale_amount" != "purchase_amount"
        assert domain_of("sale_amount") is DomainCapability.SALES
        assert domain_of("purchase_amount") is DomainCapability.PROCUREMENT

    def test_generic_roles_do_not_claim_exact_aliases(self):
        assert get_role("amount").is_generic_fallback
        assert get_role("amount").aliases == ()

    def test_artifact_role_allowlists_reference_real_roles(self):
        for kind, roles in ROLES_BY_ARTIFACT_KIND.items():
            for role in roles:
                assert get_role(role) is not None, f"{kind} references unknown role {role}"


# ── numeric parsing ─────────────────────────────────────────────────────────

class TestParseNumeric:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1,250.00 SAR", 1250.0),
            ("SAR 1,250.00", 1250.0),
            ("$99.50", 99.5),
            ("12.5", 12.5),
            ("(500.00)", -500.0),
            ("-7", -7.0),
        ],
    )
    def test_parses_currency_and_signs(self, raw, expected):
        assert parse_numeric(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", ["abc", "", "  ", "N/A", "Twelve"])
    def test_malformed_values_return_none_not_zero(self, raw):
        """A parse failure must never become 0.0 — that is a fabricated fact."""
        assert parse_numeric(raw) is None


# ── designation ─────────────────────────────────────────────────────────────

class TestGenericHeaderDesignation:
    def test_amount_designated_per_artifact_kind(self):
        assert designated_role_for("amount", "pos_export") == "sale_amount"
        assert designated_role_for("amount", "bank_statement") == "payment_amount"
        assert designated_role_for("total", "supplier_quote") == "purchase_amount"
        assert designated_role_for("amount", "expense_report") == "expense_amount"

    def test_qty_designated_per_artifact_kind(self):
        assert designated_role_for("qty", "pos_export") == "quantity"
        assert designated_role_for("qty", "purchase_order") == "purchase_quantity"
        assert designated_role_for("qty", "inventory_export") == "stock"

    def test_no_hint_means_no_designation(self):
        assert designated_role_for("amount", None) is None
        assert designated_role_for("qty", "") is None

    def test_designation_covers_every_declared_kind(self):
        for kind in GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND:
            assert get_role(GENERIC_MONEY_ROLE_BY_ARTIFACT_KIND[kind]) is not None


# ── column mapping ──────────────────────────────────────────────────────────

POS_HEADERS = ["Date", "Item", "Qty", "Unit Price", "Amount", "Branch"]
POS_ROWS = [
    ["2026-03-01", "Pepsi 330ml", 12, "1.50 SAR", "18.00 SAR", "Riyadh"],
    ["2026-03-02", "Pepsi 500ml", 8, "1.80 SAR", "14.40 SAR", "Riyadh"],
]


class TestColumnMapping:
    def test_pos_export_maps_completely(self):
        cm = map_columns(POS_HEADERS, rows=POS_ROWS, artifact_hint="pos_export")
        assert cm.ambiguous_headers == ()
        assert cm.unmapped_headers == ()
        assert cm.role_to_header == {
            "date": "Date",
            "product_name": "Item",
            "quantity": "Qty",
            "unit_price": "Unit Price",
            "sale_amount": "Amount",
            "branch_name": "Branch",
        }

    def test_currency_values_do_not_block_a_numeric_mapping(self):
        """'1.50 SAR' must be recognised as numeric, or the role loses its bonus."""
        cm = map_columns(["Unit Price"], rows=[["1.50 SAR"], ["1.80 SAR"]])
        assert cm.by_raw_header["Unit Price"].selected_role == "unit_price"

    def test_bare_amount_without_hint_is_ambiguous(self):
        """The §13 acceptance case: never pretend certainty that is not there."""
        cm = map_columns(["Item", "Amount"], rows=[["A", "10"]])
        mapping = cm.by_raw_header["Amount"]
        assert mapping.status is ColumnMappingStatus.AMBIGUOUS
        assert mapping.selected_role is None
        assert mapping.needs_review
        roles = {c.role for c in mapping.candidates}
        assert "sale_amount" in roles

    def test_amount_resolves_when_artifact_kind_disambiguates(self):
        for kind, expected in (
            ("pos_export", "sale_amount"),
            ("bank_statement", "payment_amount"),
            ("supplier_quote", "purchase_amount"),
        ):
            cm = map_columns(["Amount"], rows=[["10.00 SAR"]], artifact_hint=kind)
            assert cm.by_raw_header["Amount"].selected_role == expected, kind

    def test_bank_statement_does_not_map_description_to_product(self):
        cm = map_columns(
            ["Date", "Description", "Amount", "Balance"],
            rows=[["2026-03-01", "POS settlement", "500.00", "1200.00"]],
            artifact_hint="bank_statement",
        )
        assert "Description" in cm.unmapped_headers
        assert "product_name" not in cm.roles

    def test_unmatched_header_stays_unmapped(self):
        cm = map_columns(["Zzzzz Qqqq"], rows=[["x"]])
        assert cm.unmapped_headers == ("Zzzzz Qqqq",)
        assert cm.roles == ()

    def test_arabic_headers_map(self):
        cm = map_columns(
            ["التاريخ", "اسم المنتج", "الكمية", "السعر", "المبلغ"],
            rows=[["2026-03-01", "بيبسي", 12, "1.50", "18.00"]],
            artifact_hint="pos_export",
        )
        assert cm.by_raw_header["اسم المنتج"].selected_role == "product_name"
        assert cm.by_raw_header["الكمية"].selected_role == "quantity"

    def test_inventory_roles_map(self):
        cm = map_columns(
            ["SKU", "Item", "Current Stock", "Cost", "Unit", "Location"],
            rows=[["P1", "Pepsi", "40", "1.10 SAR", "piece", "Riyadh"]],
            artifact_hint="inventory_export",
        )
        roles = set(cm.roles)
        assert {"sku", "product_name", "stock", "cost", "unit", "location_name"} <= roles

    def test_staff_roles_map(self):
        cm = map_columns(
            ["Employee", "Shift Date", "Hours", "Status", "Branch"],
            rows=[["Sara", "2026-03-01", "8", "Present", "Riyadh"]],
            artifact_hint="staff_schedule",
        )
        assert set(cm.roles) >= {
            "employee_name", "shift_date", "shift_hours",
            "attendance_status", "branch_name",
        }

    def test_a_date_column_is_not_mapped_to_cost(self):
        """Value-shape evidence must be able to veto a plausible header match.

        A column headed "Cost" full of dates is almost certainly a mislabelled
        date column. Mapping it to ``cost`` would put dates into money fields.
        """
        cm = map_columns(
            ["Cost"], rows=[["2026-03-01"], ["2026-03-02"], ["2026-03-03"]]
        )
        mapping = cm.by_raw_header["Cost"]
        assert mapping.selected_role != "cost"
        assert mapping.status is ColumnMappingStatus.UNMAPPED
        # The veto must be explained, not silent.
        assert any("date" in reason for c in mapping.candidates for reason in c.reasons)

    def test_mapping_is_deterministic(self):
        first = map_columns(POS_HEADERS, rows=POS_ROWS, artifact_hint="pos_export")
        second = map_columns(POS_HEADERS, rows=POS_ROWS, artifact_hint="pos_export")
        assert first.to_dict() == second.to_dict()

    def test_ambiguous_mapping_preserves_candidates(self):
        cm = map_columns(["Item", "Amount"], rows=[["A", "10"]])
        mapping = cm.by_raw_header["Amount"]
        assert len(mapping.candidates) >= 2
        assert all(c.reasons for c in mapping.candidates)


# ── row roles ───────────────────────────────────────────────────────────────

class TestRowRoles:
    def test_total_row_is_not_ingestible(self):
        rows = POS_ROWS + [["Total", "", 20, "", "32.40 SAR", ""]]
        cm = map_columns(POS_HEADERS, rows=POS_ROWS, artifact_hint="pos_export")
        report = classify_rows(rows, mapped_roles=cm.role_to_header)
        total = report.classifications[-1]
        assert total.role is RowRole.TOTAL
        assert total.is_ingestible is False

    def test_subtotal_is_not_labelled_total(self):
        """"subtotal" contains "total"; a naive substring search gets this wrong."""
        report = classify_rows([["Subtotal", "", 20, "", "32.40 SAR", ""]])
        assert report.classifications[0].role is RowRole.SUBTOTAL
        assert report.classifications[0].is_ingestible is False

    def test_data_rows_are_ingestible(self):
        report = classify_rows(POS_ROWS)
        assert report.data_count == 2
        assert all(c.is_ingestible for c in report.classifications)

    def test_reconciling_total_is_verified(self):
        rows = [
            ["2026-03-01", "A", 10, "", "10.00 SAR", ""],
            ["2026-03-02", "B", 5, "", "5.00 SAR", ""],
            ["Total", "", 15, "", "15.00 SAR", ""],
        ]
        report = classify_rows(rows)
        assert report.verified_totals == (2,)
        assert report.suspicious_totals == ()

    def test_non_reconciling_total_is_reported(self):
        """A row labelled 'Total' whose numbers do not add up is suspicious."""
        rows = [
            ["2026-03-01", "A", 10, "", "10.00 SAR", ""],
            ["Total", "", 99, "", "99.00 SAR", ""],
        ]
        report = classify_rows(rows)
        assert report.suspicious_totals == (1,)
        assert report.verified_totals == ()
        assert any("do not reconcile" in n for n in report.notes)

    def test_arabic_total_row_excluded(self):
        report = classify_rows([["اجمالي", "", 3, "", "5.00 SAR", ""]])
        assert report.classifications[0].role is RowRole.TOTAL
        assert report.classifications[0].is_ingestible is False

    def test_footer_and_note_rows_excluded(self):
        report = classify_rows(
            [
                ["2026-03-01", "A", 1, "", "1.00", ""],
                ["Note: excludes returns", "", "", "", "", ""],
                ["End of report", "", "", "", "", ""],
            ]
        )
        roles = {c.role for c in report.classifications}
        assert RowRole.NOTE in roles
        assert report.data_count == 1

    def test_blank_row_is_unknown_not_data(self):
        report = classify_rows([["", "", "", "", "", ""]])
        assert report.classifications[0].role is RowRole.UNKNOWN
        assert report.data_count == 0

    def test_report_counts_add_up(self):
        rows = POS_ROWS + [["Total", "", 20, "", "32.40 SAR", ""]]
        report = classify_rows(rows)
        assert report.data_count + report.excluded_count == len(rows)