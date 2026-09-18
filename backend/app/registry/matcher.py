"""Product familiarity matcher implementing 5-tier matching priority.

Priority order:
1. exact barcode / GTIN
2. barcode + brand/generic name
3. brand + generic name + quantity
4. product-name similarity + supporting fields
5. no reliable match

CRITICAL STATUTORY SAFEGUARD:
A reference-product match is STRICTLY supporting evidence. It must never:
- Automatically produce PASS or declare legal compliance.
- Override or fabricate printed OCR findings.
- Dismiss statutory mandatory declaration requirements.
"""

from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.registry.product_registry import (
    ProductRegistry,
    ReferenceProduct,
    get_product_registry,
    _normalize_gtin,
    _normalize_text,
)

logger = logging.getLogger(__name__)

STATUTORY_DISCLAIMER = (
    "Supporting evidence only. Does not declare legal compliance or replace physical inspection."
)


@dataclass
class RegistryMatchResult:
    """Standard result structure for product familiarity matching."""

    matched: bool
    confidence: float
    confidence_percent: int
    matched_by: str
    tier: int
    tier_name: str
    suggestion_label: str
    reference_product: Optional[Dict[str, Any]] = None
    disclaimer: str = STATUTORY_DISCLAIMER
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "confidence": round(self.confidence, 2),
            "confidence_percent": self.confidence_percent,
            "matched_by": self.matched_by,
            "tier": self.tier,
            "tier_name": self.tier_name,
            "suggestion_label": self.suggestion_label,
            "reference_product": self.reference_product,
            "disclaimer": self.disclaimer,
            "notes": self.notes,
        }


def _token_similarity(a: str, b: str) -> float:
    """Compute token-based overlap similarity between two strings."""
    tokens_a = set(re.findall(r"\w+", _normalize_text(a)))
    tokens_b = set(re.findall(r"\w+", _normalize_text(b)))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(intersection) / len(union)


def _text_similarity(a: str, b: str) -> float:
    """Compute string sequence similarity between two strings."""
    norm_a = _normalize_text(a)
    norm_b = _normalize_text(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _is_field_match(observed: Optional[str], reference: Optional[str]) -> bool:
    """Check if observed field reasonably matches reference string."""
    if not observed or not reference:
        return False
    norm_obs = _normalize_text(observed)
    norm_ref = _normalize_text(reference)
    if not norm_obs or not norm_ref:
        return False
    # Exact or substring containment
    if norm_obs in norm_ref or norm_ref in norm_obs:
        return True
    return _token_similarity(norm_obs, norm_ref) >= 0.5 or _text_similarity(norm_obs, norm_ref) >= 0.65


def _is_quantity_match(
    obs_qty: Optional[str],
    ref_qty: Optional[str],
    obs_val: Optional[float] = None,
    ref_val: Optional[float] = None,
    obs_unit: Optional[str] = None,
    ref_unit: Optional[str] = None,
) -> bool:
    """Compare declared net quantity between observed package and reference."""
    if obs_val is not None and ref_val is not None:
        val_matches = abs(float(obs_val) - float(ref_val)) < 0.01
        unit_matches = _normalize_text(obs_unit) == _normalize_text(ref_unit)
        if val_matches and unit_matches:
            return True

    if obs_qty and ref_qty:
        norm_obs = re.sub(r"\s+", "", _normalize_text(obs_qty))
        norm_ref = re.sub(r"\s+", "", _normalize_text(ref_qty))
        if norm_obs == norm_ref:
            return True
        # Extract digits and unit
        m_obs = re.match(r"^([\d.]+)([a-zA-Z]+)$", norm_obs)
        m_ref = re.match(r"^([\d.]+)([a-zA-Z]+)$", norm_ref)
        if m_obs and m_ref:
            try:
                v_obs, u_obs = float(m_obs.group(1)), m_obs.group(2)
                v_ref, u_ref = float(m_ref.group(1)), m_ref.group(2)
                return abs(v_obs - v_ref) < 0.01 and u_obs == u_ref
            except ValueError:
                pass

    return False


def match_product(
    barcode: Optional[str] = None,
    brand: Optional[str] = None,
    generic_name: Optional[str] = None,
    product_name: Optional[str] = None,
    quantity: Optional[str] = None,
    quantity_value: Optional[float] = None,
    quantity_unit: Optional[str] = None,
    category: Optional[str] = None,
    registry: Optional[ProductRegistry] = None,
) -> RegistryMatchResult:
    """Match extracted package evidence against reference registry using 5-tier priority.

    Matching priority:
    1. exact barcode / GTIN
    2. barcode + brand/generic name
    3. brand + generic name + quantity
    4. product-name similarity + supporting fields
    5. no reliable match
    """
    reg = registry or get_product_registry()
    norm_barcode = _normalize_gtin(barcode)

    # -------------------------------------------------------------------------
    # Priority 1 & 2: Barcode / GTIN match
    # -------------------------------------------------------------------------
    if norm_barcode:
        ref_prod = reg.get_by_gtin(norm_barcode)
        if ref_prod:
            brand_matched = _is_field_match(brand, ref_prod.brand) or _is_field_match(product_name, ref_prod.brand)
            generic_matched = _is_field_match(generic_name, ref_prod.generic_name) or _is_field_match(product_name, ref_prod.generic_name)

            if brand_matched and generic_matched:
                # Tier 2 (Highest specificity: Barcode + Brand + Generic Name)
                return RegistryMatchResult(
                    matched=True,
                    confidence=0.94,
                    confidence_percent=94,
                    matched_by="Barcode + Brand + Generic Name",
                    tier=2,
                    tier_name="BARCODE_BRAND_GENERIC_NAME",
                    suggestion_label="Known product match",
                    reference_product=ref_prod.to_dict(),
                    notes="High confidence confirmation: barcode, brand, and generic name all align with registry.",
                )
            elif brand_matched:
                # Tier 2 (Barcode + Brand)
                return RegistryMatchResult(
                    matched=True,
                    confidence=0.94,
                    confidence_percent=94,
                    matched_by="Barcode + Brand",
                    tier=2,
                    tier_name="BARCODE_BRAND",
                    suggestion_label="Known product match",
                    reference_product=ref_prod.to_dict(),
                    notes="Barcode and brand match reference registry record.",
                )
            elif generic_matched:
                # Tier 2 (Barcode + Generic Name)
                return RegistryMatchResult(
                    matched=True,
                    confidence=0.93,
                    confidence_percent=93,
                    matched_by="Barcode + Generic Name",
                    tier=2,
                    tier_name="BARCODE_GENERIC_NAME",
                    suggestion_label="Known product match",
                    reference_product=ref_prod.to_dict(),
                    notes="Barcode and generic commodity name match reference registry record.",
                )
            else:
                # Tier 1 (Exact Barcode / GTIN alone)
                return RegistryMatchResult(
                    matched=True,
                    confidence=0.92,
                    confidence_percent=92,
                    matched_by="Exact Barcode / GTIN",
                    tier=1,
                    tier_name="EXACT_BARCODE",
                    suggestion_label="Known product match",
                    reference_product=ref_prod.to_dict(),
                    notes="Exact barcode matched in reference catalog; package label text awaiting verification.",
                )

    # -------------------------------------------------------------------------
    # Priority 3: Brand + generic name + quantity (No barcode match required)
    # -------------------------------------------------------------------------
    all_products = reg.get_all()
    if brand and (generic_name or product_name):
        for ref in all_products:
            brand_ok = _is_field_match(brand, ref.brand)
            generic_ok = _is_field_match(generic_name, ref.generic_name) or _is_field_match(product_name, ref.generic_name)
            qty_ok = _is_quantity_match(
                obs_qty=quantity,
                ref_qty=ref.declared_net_quantity,
                obs_val=quantity_value,
                ref_val=ref.net_quantity_value,
                obs_unit=quantity_unit,
                ref_unit=ref.net_quantity_unit,
            )

            if brand_ok and generic_ok and qty_ok:
                return RegistryMatchResult(
                    matched=True,
                    confidence=0.88,
                    confidence_percent=88,
                    matched_by="Brand + Generic Name + Quantity",
                    tier=3,
                    tier_name="BRAND_GENERIC_QUANTITY",
                    suggestion_label="Known product match",
                    reference_product=ref.to_dict(),
                    notes="Brand, commodity name, and declared quantity align with reference specification.",
                )

    # -------------------------------------------------------------------------
    # Priority 4: Product-name similarity + supporting fields
    # -------------------------------------------------------------------------
    best_candidate: Optional[ReferenceProduct] = None
    best_score: float = 0.0
    best_matched_fields: List[str] = []

    for ref in all_products:
        name_sim = 0.0
        if product_name:
            name_sim = max(
                _text_similarity(product_name, ref.product_name),
                _token_similarity(product_name, ref.product_name),
            )

        if name_sim < 0.55:
            continue

        supporting_score = 0.0
        matched_fields = ["Product Name Similarity"]

        # Supporting field: category
        if category and _normalize_text(category) == _normalize_text(ref.category):
            supporting_score += 0.10
            matched_fields.append("Category")

        # Supporting field: brand
        if brand and _is_field_match(brand, ref.brand):
            supporting_score += 0.15
            matched_fields.append("Brand")

        # Supporting field: quantity
        if _is_quantity_match(
            obs_qty=quantity,
            ref_qty=ref.declared_net_quantity,
            obs_val=quantity_value,
            ref_val=ref.net_quantity_value,
            obs_unit=quantity_unit,
            ref_unit=ref.net_quantity_unit,
        ):
            supporting_score += 0.15
            matched_fields.append("Quantity")

        total_score = min(0.85, (name_sim * 0.6) + supporting_score)
        if total_score > best_score and total_score >= 0.70:
            best_score = total_score
            best_candidate = ref
            best_matched_fields = matched_fields

    if best_candidate and best_score >= 0.70:
        conf_pct = int(round(best_score * 100))
        matched_by_str = " + ".join(best_matched_fields) if len(best_matched_fields) > 1 else "Product-name similarity"
        return RegistryMatchResult(
            matched=True,
            confidence=round(best_score, 2),
            confidence_percent=conf_pct,
            matched_by=matched_by_str,
            tier=4,
            tier_name="PRODUCT_NAME_SIMILARITY",
            suggestion_label="Known product match",
            reference_product=best_candidate.to_dict(),
            notes=f"Identified via text similarity ({conf_pct}%) supported by packaging metadata.",
        )

    # -------------------------------------------------------------------------
    # Priority 5: No reliable match
    # -------------------------------------------------------------------------
    return RegistryMatchResult(
        matched=False,
        confidence=0.0,
        confidence_percent=0,
        matched_by="No reliable match",
        tier=5,
        tier_name="NO_MATCH",
        suggestion_label="No reliable match",
        reference_product=None,
        notes="No known product in reference registry matches observed package declarations.",
    )


def improve_candidate_ranking(
    field_name: str,
    candidates: List[Dict[str, Any]],
    reference_product: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Annotate and rank candidates using reference product as supporting context.

    CRITICAL: Does NOT alter candidate text or fabricate evidence.
    Sets is_reference_match=True and positions matching candidates favorably.
    """
    if not candidates or not reference_product:
        return candidates

    ref_val = ""
    if field_name == "PRODUCT_NAME":
        ref_val = reference_product.get("product_name") or ""
    elif field_name in ("BRAND", "BRAND_NAME"):
        ref_val = reference_product.get("brand") or ""
    elif field_name in ("GENERIC_NAME", "COMMODITY_NAME"):
        ref_val = reference_product.get("generic_name") or ""
    elif field_name == "DECLARED_NET_QUANTITY":
        ref_val = reference_product.get("declared_net_quantity") or ""
    elif field_name == "MANUFACTURER_NAME":
        ref_val = reference_product.get("manufacturer_name") or ""

    if not ref_val:
        return candidates

    ranked = []
    for cand in candidates:
        cand_dict = dict(cand) if isinstance(cand, dict) else {"value": str(cand)}
        cand_val = str(cand_dict.get("value") or cand_dict.get("raw_text") or "")
        if cand_val and _is_field_match(cand_val, ref_val):
            cand_dict["is_reference_match"] = True
            cand_dict["reference_supporting_value"] = ref_val
        else:
            cand_dict.setdefault("is_reference_match", False)
        ranked.append(cand_dict)

    # Sort matching candidates first while preserving relative order
    ranked.sort(key=lambda x: not x.get("is_reference_match", False))
    return ranked
