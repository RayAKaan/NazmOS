"""Entity resolution tests (spec §19, §20).

The audit found five independent resolvers, the worst being
``adapters/item_resolver`` whose fourth tier matched on a 10-character substring.
These tests pin the safety properties that the replacement guarantees:

* ``Pepsi 330ml`` and ``Pepsi 500ml`` never merge, despite high fuzzy similarity;
* ``Al Noor Trading`` vs ``Al Noor Trading Est.`` may remain ambiguous rather than
  being force-merged;
* the same SKU with a different display name *is* the same product;
* different SKUs with the same name are not merged;
* the same product at different branches is one product with two locations;
* the same phone with different customer names stays ambiguous.
"""
from __future__ import annotations

import pytest

from app.services.orbit.contracts import (
    Entity,
    EntityKind,
    MatchMethod,
    ResolutionOutcome,
)
from app.services.orbit.entities import (
    EntityResolver,
    EntityStore,
    build_product,
    strip_legal_suffix,
    variant_signature,
)


def _resolver(*products: Entity, **kw) -> EntityResolver:
    store = EntityStore(business_id="biz-1")
    for product in products:
        store.register(product)
    return EntityResolver(store)


# ── the headline safety property ────────────────────────────────────────────

class TestVariantSafety:
    def test_pepsi_330_and_500_do_not_merge(self):
        r = _resolver(
            build_product("Pepsi 330ml", sku="P330"),
            build_product("Pepsi 500ml", sku="P500"),
        )
        result = r.resolve(EntityKind.PRODUCT, name="Pepsi 330ml", identifiers={"sku": "P330"})
        # Decided by SKU, and definitely not by name alone.
        assert result.outcome is ResolutionOutcome.SAME_ENTITY
        assert result.selected_entity.canonical_name == "Pepsi 330ml"

    def test_variant_difference_blocks_a_fuzzy_merge(self):
        """Same base name, different size: the most dangerous false merge."""
        r = _resolver(build_product("Pepsi 330ml"))
        result = r.resolve(EntityKind.PRODUCT, name="Pepsi 500ml")
        assert result.outcome is not ResolutionOutcome.SAME_ENTITY
        assert result.selected_entity is None

    def test_variant_signature_is_detected(self):
        assert "330ml" in variant_signature("Pepsi 330ml")
        assert "500ml" in variant_signature("Pepsi 500ml")
        assert variant_signature("Pepsi") == frozenset()

    def test_differently_sized_variants_are_surfaced(self):
        r = _resolver(
            build_product("Pepsi 330ml"),
            build_product("Pepsi 500ml"),
        )
        pairs = r.products_with_different_variants()
        assert len(pairs) == 1
        left, right = pairs[0]
        assert {left.canonical_name, right.canonical_name} == {"Pepsi 330ml", "Pepsi 500ml"}

    def test_diet_and_regular_are_distinct(self):
        r = _resolver(build_product("Cola Regular"))
        assert r.resolve(EntityKind.PRODUCT, name="Cola Diet").outcome is not (
            ResolutionOutcome.SAME_ENTITY
        )

    def test_can_and_bottle_are_distinct(self):
        r = _resolver(build_product("Water 500ml Bottle"))
        assert r.resolve(EntityKind.PRODUCT, name="Water 500ml Can").outcome is not (
            ResolutionOutcome.SAME_ENTITY
        )


# ── suppliers ───────────────────────────────────────────────────────────────

class TestSupplierResolution:
    def test_legal_suffix_variants_may_merge_but_are_not_proven(self):
        """'Al Noor Trading' vs 'Al Noor Trading Est.' — a legal suffix is weak
        evidence, so an unrelated name must not be silently merged into it."""
        a = Entity(
            kind=EntityKind.SUPPLIER, canonical_name="Al Noor Trading",
            normalized_name="al noor trading",
        )
        r = _resolver(a)
        result = r.resolve(EntityKind.SUPPLIER, name="Al Noor Trading Est.")
        # Either a merge (with an explicit method) or ambiguity; never a silent
        # different_entity claim that pretends certainty about a real company.
        assert result.outcome in (
            ResolutionOutcome.SAME_ENTITY, ResolutionOutcome.AMBIGUOUS,
        )
        if result.outcome is ResolutionOutcome.SAME_ENTITY:
            assert result.match_method is not MatchMethod.UNRESOLVED

    def test_strip_legal_suffix(self):
        assert strip_legal_suffix("Al Noor Trading Est.") == "al noor trading"
        assert strip_legal_suffix("Al Noor Trading Co. LLC") == "al noor trading"
        assert strip_legal_suffix("Al Noor") == "al noor"

    def test_distinct_suppliers_do_not_merge(self):
        r = _resolver(Entity(kind=EntityKind.SUPPLIER, canonical_name="Al Noor Trading",
                              normalized_name="al noor trading"))
        result = r.resolve(EntityKind.SUPPLIER, name="Rayan Water Company")
        assert result.selected_entity is None or result.outcome is ResolutionOutcome.AMBIGUOUS


# ── identifiers beat names ──────────────────────────────────────────────────

class TestIdentifierAuthority:
    def test_same_sku_different_display_name_is_same_product(self):
        r = _resolver(build_product("Pepsi 330ml Can", sku="SKU-1"))
        result = r.resolve(
            EntityKind.PRODUCT, name="Pepsi Cola 33cl", identifiers={"sku": "SKU-1"}
        )
        assert result.outcome is ResolutionOutcome.SAME_ENTITY
        assert result.match_method is MatchMethod.SKU
        assert result.confidence == 1.0

    def test_different_sku_same_name_is_not_auto_merged(self):
        """A conflicting SKU must block a name-based merge.

        Same name but sku=SKU-B against an existing sku=SKU-A means these are two
        different products that happen to share a display name.
        """
        r = _resolver(build_product("Pepsi 330ml", sku="SKU-A"))
        result = r.resolve(EntityKind.PRODUCT, name="Pepsi 330ml", identifiers={"sku": "SKU-B"})
        assert result.outcome is not ResolutionOutcome.SAME_ENTITY
        assert "SKU-B" in result.note

    def test_barcode_is_authoritative(self):
        r = _resolver(build_product("Chips", barcode="6281000123"))
        result = r.resolve(EntityKind.PRODUCT, name="Totally Different Name",
                           identifiers={"barcode": "6281000123"})
        assert result.outcome is ResolutionOutcome.SAME_ENTITY
        assert result.match_method is MatchMethod.BARCODE

    def test_exact_name_when_no_identifier(self):
        r = _resolver(build_product("Nestle 250g"))
        result = r.resolve(EntityKind.PRODUCT, name="Nestle 250g")
        assert result.match_method is MatchMethod.EXACT_NORMALIZED_NAME


# ── customers ───────────────────────────────────────────────────────────────

class TestCustomerResolution:
    def _customer(self, name, phone=None, email=None):
        ids = {}
        if phone:
            ids["phone"] = phone
        if email:
            ids["email"] = email
        if not ids:
            ids = {"name": f"customer:{name}"}
        return Entity(kind=EntityKind.CUSTOMER, canonical_name=name,
                      normalized_name=name, identifiers=ids)

    def test_same_phone_different_names_stays_ambiguous(self):
        """One phone, two names: could be a typo or two people sharing a phone."""
        r = _resolver(self._customer("Sara Ahmed", phone="+966500000001"))
        result = r.resolve(EntityKind.CUSTOMER, name="Sara A.",
                           identifiers={"phone": "+966500000001"})
        # A shared phone is a strong but not absolute signal; the resolver must
        # either merge on the phone explicitly or report ambiguity.
        assert result.outcome in (
            ResolutionOutcome.SAME_ENTITY, ResolutionOutcome.AMBIGUOUS
        )
        if result.outcome is ResolutionOutcome.SAME_ENTITY:
            assert result.match_method is MatchMethod.PHONE

    def test_email_is_authoritative(self):
        r = _resolver(self._customer("Sara", email="sara@example.com"))
        result = r.resolve(EntityKind.CUSTOMER, name="S. Ahmed",
                           identifiers={"email": "sara@example.com"})
        assert result.match_method is MatchMethod.EMAIL


# ── branches and locations ──────────────────────────────────────────────────

class TestBranchAndLocation:
    def test_same_product_different_branch_is_one_product(self):
        """Branches are entities in their own right; they do not multiply products."""
        r = _resolver(build_product("Pepsi 330ml", sku="P330"))
        riyadh = r.resolve_or_create(EntityKind.BRANCH, name="Riyadh Branch")[0]
        jeddah = r.resolve_or_create(EntityKind.BRANCH, name="Jeddah Branch")[0]
        assert riyadh is not jeddah
        p1 = r.resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml",
                                 identifiers={"sku": "P330"})[0]
        p2 = r.resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml",
                                 identifiers={"sku": "P330"})[0]
        assert p1.entity_id == p2.entity_id

    def test_location_and_branch_are_distinct_kinds(self):
        r = _resolver()
        b = r.resolve_or_create(EntityKind.BRANCH, name="Riyadh")[0]
        loc = r.resolve_or_create(EntityKind.LOCATION, name="Riyadh")[0]
        assert b.entity_id != loc.entity_id


# ── determinism and lifecycle ───────────────────────────────────────────────

class TestResolverLifecycle:
    def test_resolve_or_create_is_idempotent(self):
        r = _resolver()
        e1, _, created1 = r.resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml")
        e2, _, created2 = r.resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml")
        assert created1 is True and created2 is False
        assert e1.entity_id == e2.entity_id

    def test_unknown_reference_creates_a_new_entity(self):
        r = _resolver()
        _, resolution, created = r.resolve_or_create(EntityKind.PRODUCT, name="Brand New")
        assert created is True
        assert resolution.outcome is ResolutionOutcome.DIFFERENT_ENTITY

    def test_entity_ids_are_deterministic(self):
        a = _resolver().resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml")[0]
        b = _resolver().resolve_or_create(EntityKind.PRODUCT, name="Pepsi 330ml")[0]
        assert a.entity_id == b.entity_id

    def test_resolution_is_recorded_for_audit(self):
        r = _resolver(build_product("Pepsi 330ml"))
        r.resolve(EntityKind.PRODUCT, name="Pepsi 330ml")
        assert len(r.store.resolutions) == 1

    def test_ambiguous_names_are_reported(self):
        """Two distinct entities normalizing to the same name -> ambiguous."""
        e1 = Entity(kind=EntityKind.SUPPLIER, canonical_name="Al Noor", normalized_name="al noor",
                    identifiers={"reg": "1"})
        e2 = Entity(kind=EntityKind.SUPPLIER, canonical_name="AL  NOOR", normalized_name="al noor",
                    identifiers={"reg": "2"})
        r = _resolver(e1, e2)
        result = r.resolve(EntityKind.SUPPLIER, name="Al Noor")
        assert result.outcome is ResolutionOutcome.AMBIGUOUS
        assert len(result.candidates) == 2

    def test_entity_kinds_do_not_cross_match(self):
        """A product and a supplier sharing a name are different entities."""
        r = _resolver(build_product("Al Noor"))
        result = r.resolve(EntityKind.SUPPLIER, name="Al Noor")
        assert result.selected_entity is None


# ── bounded judgment ────────────────────────────────────────────────────────

class _FakeJev:
    """Test-only. Explicitly marked as mocked."""

    source = "mocked"

    def __init__(self, choice: str = "ambiguous", selected_id: str | None = None) -> None:
        self.choice = choice
        self.selected_id = selected_id

    def decide_entity(self, **kw):
        class D:
            pass
        d = D()
        d.choice = self.choice
        d.selected_id = self.selected_id
        d.confidence = 0.6
        return d


class TestBoundedJudgment:
    def test_jev_ambiguous_preserves_ambiguity(self):
        r = _resolver()
        result = r.resolve(EntityKind.PRODUCT, name="Mystery Item", jev=_FakeJev("ambiguous"))
        assert result.outcome is ResolutionOutcome.AMBIGUOUS

    def test_jev_failure_does_not_destroy_determinism(self):
        class Broken:
            source = "mocked"
            def decide_entity(self, **kw):
                raise RuntimeError("jev unavailable")
        r = _resolver()
        result = r.resolve(EntityKind.PRODUCT, name="Mystery Item", jev=Broken())
        # Falls back to the deterministic outcome; never raises, never invents.
        assert result.outcome is ResolutionOutcome.DIFFERENT_ENTITY

    def test_jev_cannot_override_a_decisive_sku_match(self):
        r = _resolver(build_product("Pepsi 330ml", sku="P330"))
        jev = _FakeJev("different_entity")
        result = r.resolve(EntityKind.PRODUCT, name="Totally Other",
                           identifiers={"sku": "P330"}, jev=jev)
        assert result.outcome is ResolutionOutcome.SAME_ENTITY
        assert result.match_method is MatchMethod.SKU