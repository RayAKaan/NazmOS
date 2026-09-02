"""ReasoningCapsule integrity: hashing, signing, freshness, decision sets."""
from app.security.capsule import CapsuleItem, CapsuleSigner, ReasoningCapsule
from app.security.privacy_firewall import build_capsule_for_payload


def _capsule(**kw) -> ReasoningCapsule:
    item = CapsuleItem(
        ref="item_A",
        classification="slow_mover",
        stock_band="50-199",
        velocity_band="LOW",
        candidate_decisions=["DO_NOTHING", "DISCOUNT", "TRANSFER"],
        evidence_fields=["stock_band", "velocity_band", "classification"],
    )
    base = dict(capability="test", purpose="_internal", items=[item])
    base.update(kw)
    return ReasoningCapsule.new(**base)


def test_canonical_json_is_stable():
    c1 = _capsule()
    # Serialization -> parse -> re-serialize must be byte-identical.
    reloaded = ReasoningCapsule.model_validate(c1.model_dump(mode="json"))
    assert c1.canonical_bytes() == reloaded.canonical_bytes()
    # And signing does not change the canonical payload.
    signed = CapsuleSigner().sign(c1)
    assert signed.capsule_hash == __import__("hashlib").sha256(c1.canonical_bytes()).hexdigest()


def test_sign_then_verify():
    capsule = CapsuleSigner().sign(_capsule())
    assert capsule.capsule_hash
    assert capsule.signature
    assert CapsuleSigner().verify(capsule) is True


def test_tampered_signature_rejected():
    capsule = CapsuleSigner().sign(_capsule())
    # Any change to the business or item state breaks the signature.
    capsule.items[0].stock_band = "200-499"
    assert CapsuleSigner().verify(capsule) is False


def test_capsule_defaults_fresh_and_expiry_detection():
    from datetime import timedelta

    capsule = _capsule()
    assert capsule.is_fresh() is True

    expired = _capsule()
    expired.issued_at = expired.issued_at - timedelta(seconds=10_000)
    expired.expires_at = expired.expires_at - timedelta(seconds=10_000)
    assert expired.is_expired() is True
    assert expired.is_fresh() is False


def test_allowed_decisions_unions_candidates():
    capsule = _capsule()
    allowed = capsule.allowed_decisions()
    assert {"DO_NOTHING", "MANUAL_REVIEW", "DISCOUNT", "TRANSFER"} <= allowed
    assert "REORDER" not in allowed


def test_allowed_evidence_includes_opaque_refs_and_signals():
    capsule = _capsule()
    ev = capsule.allowed_evidence()
    assert "item_A" in ev
    assert "item_A.stock_band" in ev
    assert "deterministic_decision" in ev


def test_blob_has_no_hash_after_resign_is_signed():
    capsule = CapsuleSigner().sign(_capsule())
    blob_str = str(capsule.blob())
    assert capsule.capsule_hash in blob_str  # hash included for binding