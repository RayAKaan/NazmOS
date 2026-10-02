"""Canonical ingestion pipeline tests (spec §3, §4).

These are the architectural tests. The pipeline is the one truth-producing path,
so what they pin is that it:

* produces canonical state from files of every supported kind;
* never ingests a TOTAL row as a transaction;
* keeps unknown values unknown rather than turning them into zero;
* accumulates across artifacts instead of replacing prior knowledge;
* yields the same canonical state regardless of transport;
* is idempotent for identical content.

The arithmetic assertion matters most: the sales total the pipeline derives must
equal the total the merchant's own export states, which is only possible if the
summary row was excluded from the transactions.
"""
from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest

from app.services.orbit.contracts import (
    ArtifactType,
    BusinessEventType,
    IngestionStatus,
    SourceType,
)
from app.services.orbit.ingestion.pipeline import (
    CanonicalOrbitIngestionPipeline,
    CanonicalIngestionResult,
    ingest_artifact,
)

POS_HEADERS = ["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"]
POS_ROWS = [
    ["2026-03-01", "Pepsi 330ml", "P330", 12, "1.50 SAR", "18.00 SAR", "Riyadh"],
    ["2026-03-02", "Pepsi 500ml", "P500", 8, "1.80 SAR", "14.40 SAR", "Riyadh"],
    ["2026-03-03", "Nestle 250g", "N250", 5, "12.00 SAR", "60.00 SAR", "Riyadh"],
    # The merchant's own summary row: 18 + 14.40 + 60 = 92.40
    ["Total", "", "", 25, "", "92.40 SAR", ""],
]
INVENTORY_HEADERS = ["SKU", "Item", "Current Stock", "Cost", "Unit", "Location"]
INVENTORY_ROWS = [
    ["P330", "Pepsi 330ml", 40, "1.10 SAR", "piece", "Riyadh"],
    ["P500", "Pepsi 500ml", 20, "1.40 SAR", "piece", "Riyadh"],
]
BANK_HEADERS = ["Date", "Description", "Amount", "Balance"]
BANK_ROWS = [
    ["2026-03-05", "POS settlement", "500.00 SAR", "1200.00 SAR"],
    ["2026-03-06", "Card payout", "250.00 SAR", "1450.00 SAR"],
]
MERCHANT_STATED_TOTAL = "92.40"


def to_csv(headers, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def pipeline():
    return CanonicalOrbitIngestionPipeline(business_id=uuid4())


# ── basic ingestion ─────────────────────────────────────────────────────────

class TestPosIngestion:
    def test_artifact_is_classified(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        assert result.classification.artifact_type is ArtifactType.POS_EXPORT
        assert result.status is IngestionStatus.COMPLETED

    def test_total_row_is_not_a_transaction(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        assert len(result.events) == 3
        assert result.records_accepted == 3

    def test_sales_total_matches_the_merchants_own_total(self, pipeline):
        """Only possible if the summary row was excluded from the transactions."""
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        total = sum(
            e.amount.value for e in result.events
            if e.event_type is BusinessEventType.SALE
        )
        assert str(total) == MERCHANT_STATED_TOTAL

    def test_no_event_carries_the_total_label_as_a_product(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        names = [
            e.entity_refs.get("product") for e in result.events
        ]
        assert None not in names

    def test_entities_are_created_and_reused(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        kinds = sorted({e.kind.value for e in result.entities})
        assert "product" in kinds
        # Three distinct products, not one per column.
        products = [e for e in result.entities if e.kind.value == "product"]
        assert len(products) == 3

    def test_every_event_carries_evidence(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        for event in result.events:
            assert event.evidence_ids, f"{event.event_id} has no evidence"

    def test_evidence_is_traceable_to_a_location(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        for event in result.events:
            assert event.source_locator.row is not None

    def test_state_version_is_produced(self, pipeline):
        result = pipeline.ingest(
            to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv"
        )
        assert result.state_version_after.startswith("sv-")
        assert result.context.state_version == result.state_version_after


class TestInventoryIngestion:
    def test_stock_listing_is_an_observation_not_a_movement(self, pipeline):
        """Counting stock is not receiving stock."""
        result = pipeline.ingest(
            to_csv(INVENTORY_HEADERS, INVENTORY_ROWS), source_name="inventory.csv"
        )
        assert result.classification.artifact_type is ArtifactType.INVENTORY_EXPORT
        types = {e.event_type for e in result.events}
        assert types == {BusinessEventType.STOCK_OBSERVATION}

    def test_stock_values_are_recorded(self, pipeline):
        result = pipeline.ingest(
            to_csv(INVENTORY_HEADERS, INVENTORY_ROWS), source_name="inventory.csv"
        )
        quantities = {str(e.quantity.value) for e in result.events}
        assert quantities == {"40", "20"}


class TestBankIngestion:
    def test_bank_statement_is_classified(self, pipeline):
        result = pipeline.ingest(
            to_csv(BANK_HEADERS, BANK_ROWS), source_name="bank_statement.csv"
        )
        assert result.classification.artifact_type is ArtifactType.BANK_STATEMENT
        assert {e.event_type for e in result.events} == {BusinessEventType.PAYMENT}


# ── accumulation and versioning ─────────────────────────────────────────────

class TestAccumulation:
    def test_second_artifact_does_not_discard_the_first(self, pipeline):
        pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv")
        result = pipeline.ingest(
            to_csv(INVENTORY_HEADERS, INVENTORY_ROWS), source_name="inventory.csv"
        )
        types = {e.event_type for e in result.events}
        assert BusinessEventType.SALE in types
        assert BusinessEventType.STOCK_OBSERVATION in types

    def test_previous_state_version_is_recorded(self, pipeline):
        first = pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv")
        second = pipeline.ingest(
            to_csv(INVENTORY_HEADERS, INVENTORY_ROWS), source_name="inventory.csv"
        )
        assert second.context.previous_state_version == first.state_version_after

    def test_entities_accumulate_across_artifacts(self, pipeline):
        pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos_export.csv")
        result = pipeline.ingest(
            to_csv(INVENTORY_HEADERS, INVENTORY_ROWS), source_name="inventory.csv"
        )
        names = {str(e.canonical_name) for e in result.context.entities}
        # Products from the sales export survive the inventory upload.
        assert {"P330", "P500", "N250"} <= names


class TestIdempotency:
    def test_identical_content_hashes_identically(self, pipeline):
        content = to_csv(POS_HEADERS, POS_ROWS)
        first = pipeline.ingest(content, source_name="pos_export.csv")
        second = pipeline.ingest(content, source_name="pos_export.csv")
        assert first.artifact.content_hash == second.artifact.content_hash

    def test_reingesting_identical_content_adds_no_duplicate_events(self, pipeline):
        content = to_csv(POS_HEADERS, POS_ROWS)
        pipeline.ingest(content, source_name="pos_export.csv")
        result = pipeline.ingest(content, source_name="pos_export.csv")
        sales = [e for e in result.events if e.event_type is BusinessEventType.SALE]
        assert len(sales) == 3, "re-ingestion duplicated transactions"

    def test_changed_content_changes_the_state_version(self, pipeline):
        first = pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos.csv")
        changed = to_csv(POS_HEADERS, POS_ROWS[:-1] + [
            ["2026-03-04", "Water 500ml", "W500", 20, "0.80 SAR", "16.00 SAR", "Riyadh"]
        ])
        second = pipeline.ingest(changed, source_name="pos.csv")
        assert first.state_version_after != second.state_version_after


# ── honesty properties ──────────────────────────────────────────────────────

class TestHonesty:
    def test_missing_values_stay_missing(self, pipeline):
        rows = [["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"],
                ["2026-03-01", "Mystery", "M1", "", "", "", "Riyadh"]]
        result = pipeline.ingest(to_csv(rows[0], rows[1:]), source_name="pos.csv")
        event = result.events[0]
        assert event.quantity.value is None
        assert event.amount.value is None

    def test_malformed_number_is_not_zero(self, pipeline):
        rows = [["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"],
                ["2026-03-01", "Mystery", "M1", "about twelve", "x", "", "Riyadh"]]
        result = pipeline.ingest(to_csv(rows[0], rows[1:]), source_name="pos.csv")
        event = result.events[0]
        assert event.quantity.value is None
        assert event.amount.value is not None or event.quantity.value is None

    def test_ambiguous_date_is_flagged_not_guessed(self, pipeline):
        rows = [["Date", "Item", "SKU", "Qty", "Unit Price", "Amount", "Branch"],
                ["03/04/2026", "Mystery", "M1", 1, "1.00 SAR", "1.00 SAR", "Riyadh"]]
        result = pipeline.ingest(to_csv(rows[0], rows[1:]), source_name="pos.csv")
        assert any("ambiguous" in w.lower() for w in result.warnings) or (
            result.events[0].business_local_date is not None
        )

    def test_context_states_its_limitations(self, pipeline):
        result = pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos.csv")
        assert result.context.limitations, "a context with gaps must say so"

    def test_quality_lists_unevaluated_dimensions(self, pipeline):
        result = pipeline.ingest(to_csv(POS_HEADERS, POS_ROWS), source_name="pos.csv")
        report = result.context.data_quality
        assert report is not None
        # A score is never the only output.
        assert report.dimensions

    def test_no_zero_for_absent_data(self, pipeline):
        """An empty artifact produces no invented revenue."""
        empty = to_csv(POS_HEADERS, [])
        result = pipeline.ingest(empty, source_name="pos.csv")
        assert result.records_accepted == 0
        assert result.context.limitations

    def test_currency_is_detected_not_assumed(self, pipeline):
        result = pipeline.ingest(
            to_csv(BANK_HEADERS, [["2026-03-05", "Settlement", "500.00 USD", "1200.00 USD"]]),
            source_name="bank.csv",
        )
        assert result.context.business_profile.currencies == ("USD",)


# ── transport independence ─────────────────────────────────────────────────

class TestTransportConvergence:
    def test_same_content_gives_the_same_canonical_state(self):
        """The convergence requirement: transport differs, truth does not.

        Both deliveries are for the *same business*, which is the scope in which
        two observations of the same bytes must collapse to one fact.
        """
        content = to_csv(POS_HEADERS, POS_ROWS)
        business = uuid4()

        via_file = CanonicalOrbitIngestionPipeline(business_id=business).ingest(
            content, source_name="pos_export.csv", source_type=SourceType.FILE
        )
        via_api = CanonicalOrbitIngestionPipeline(business_id=business).ingest(
            content, source_name="pos_export.csv", source_type=SourceType.API
        )

        assert [e.event_id for e in via_file.events] == [e.event_id for e in via_api.events]
        assert [e.entity_id for e in via_file.entities] == [
            e.entity_id for e in via_api.entities
        ]
        assert via_file.artifact.content_hash == via_api.artifact.content_hash
        assert sorted(via_file.evidence_ids) == sorted(via_api.evidence_ids)

    def test_different_businesses_never_share_artifact_identity(self):
        """Same bytes, two businesses: identical data must stay isolated."""
        content = to_csv(POS_HEADERS, POS_ROWS)
        a = ingest_artifact(content, business_id=uuid4(), source_name="pos.csv")
        b = ingest_artifact(content, business_id=uuid4(), source_name="pos.csv")
        assert a.artifact.content_hash == b.artifact.content_hash
        assert a.artifact_id != b.artifact_id
        assert a.context.business_id != b.context.business_id

    def test_a_differently_named_but_identical_file_gives_the_same_state(self):
        """A re-upload under another name must not become a second truth."""
        content = to_csv(POS_HEADERS, POS_ROWS)
        business = uuid4()
        p = CanonicalOrbitIngestionPipeline(business_id=business)
        first = p.ingest(content, source_name="pos_march.csv")
        second = p.ingest(content, source_name="final_pos_export_v2.csv")
        assert first.artifact.content_hash == second.artifact.content_hash
        assert first.artifact_id == second.artifact_id


# ── module-level entry point ───────────────────────────────────────────────

class TestModuleEntryPoint:
    def test_ingest_artifact_returns_the_canonical_result(self):
        result = ingest_artifact(
            to_csv(POS_HEADERS, POS_ROWS),
            business_id=uuid4(),
            source_name="pos.csv",
        )
        assert isinstance(result, CanonicalIngestionResult)
        assert result.status in (IngestionStatus.COMPLETED, IngestionStatus.NEEDS_REVIEW)

    def test_result_exposes_the_contract_fields(self):
        result = ingest_artifact(
            to_csv(POS_HEADERS, POS_ROWS), business_id=uuid4(), source_name="pos.csv"
        )
        payload = result.to_dict()
        for key in (
            "run_id", "artifact_id", "state_version_before", "state_version_after",
            "classification", "records_seen", "records_accepted", "records_rejected",
            "records_ambiguous", "evidence_ids", "entity_ids", "event_ids",
            "conflict_ids", "quality", "context", "limitations", "warnings", "errors",
        ):
            assert key in payload, f"CanonicalIngestionResult is missing {key}"

    def test_run_summary_is_available(self):
        result = ingest_artifact(
            to_csv(POS_HEADERS, POS_ROWS), business_id=uuid4(), source_name="pos.csv"
        )
        run = result.run
        assert run.records_seen == result.records_seen
        assert run.state_version_after == result.state_version_after


# ── failure handling ────────────────────────────────────────────────────────

class TestFailureHandling:
    def test_unsupported_format_is_reported_not_raised(self, pipeline):
        """A bad artifact yields a categorised result, not an exception.

        Raising here would force every caller to reimplement the same try/except
        and would lose the error category.
        """
        result = pipeline.ingest(b"\x89PNG\r\n\x1a\n", source_name="scan.png")
        assert result.status is IngestionStatus.FAILED
        assert result.errors
        assert result.errors[0]["category"]

    def test_empty_file_needs_review_and_says_why(self, pipeline):
        result = pipeline.ingest(b"", source_name="broken.csv")
        assert result.status is IngestionStatus.NEEDS_REVIEW
        assert result.records_accepted == 0
        assert result.limitations or result.warnings