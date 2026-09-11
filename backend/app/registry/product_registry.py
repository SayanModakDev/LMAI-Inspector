"""Reference Product Registry — generic, extensible product familiarity layer.

Designed for Government of India Legal Metrology inspection deployment.
Stores reference packaging identity data (GTIN, brand, generic name, standard quantity,
manufacturer details) from national registries or previous verified inspections.

CRITICAL STATUTORY BOUNDARY:
A reference product match is supporting evidence ONLY. It must NEVER produce an
automatic statutory PASS, waive mandatory declarations, or replace inspector physical verification.
"""

from dataclasses import dataclass, asdict
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "data", "reference_products.json"
)


def _normalize_gtin(gtin: Optional[str]) -> str:
    """Normalize barcode/GTIN to bare digits, removing whitespace or hyphens."""
    if not gtin:
        return ""
    return re.sub(r"\D", "", str(gtin).strip())


def _normalize_text(text: Optional[str]) -> str:
    """Normalize text for consistent comparison: lowercase, stripped, collapsed spaces."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip().lower())


@dataclass
class ReferenceProduct:
    """Standard representation of a known packaged commodity in the registry."""

    gtin: str
    product_name: str
    brand: str
    generic_name: Optional[str] = None
    category: str = "FOOD"
    product_type: Optional[str] = None
    package_type: str = "RETAIL"
    declared_net_quantity: Optional[str] = None
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    standard_mrp: Optional[str] = None
    manufacturer_name: Optional[str] = None
    manufacturer_address: Optional[str] = None
    fssai_license: Optional[str] = None
    source: str = "NATIONAL_PRODUCT_REGISTRY"
    verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReferenceProduct":
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)


class ProductRegistry:
    """Extensible in-memory registry of known reference products with file persistence.

    Suitable for future integration with Government databases (e.g. GS1 DataKart,
    National Legal Metrology Portal, FSSAI FoSCoS).
    """

    def __init__(self, data_file: Optional[str] = None):
        self.data_file = data_file or DEFAULT_DATA_PATH
        self._by_gtin: Dict[str, ReferenceProduct] = {}
        self._all_products: List[ReferenceProduct] = []
        self._version: str = "1.0.0"
        self._authority: str = "Legal Metrology Reference Data Division"
        self.load()

    def load(self, file_path: Optional[str] = None) -> None:
        """Load registry from JSON file."""
        target_path = file_path or self.data_file
        if not os.path.exists(target_path):
            logger.info("Registry file %s does not exist; starting with empty registry.", target_path)
            return

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            self._version = payload.get("version", "1.0.0")
            self._authority = payload.get("authority", "Legal Metrology Reference Data Division")
            self._by_gtin.clear()
            self._all_products.clear()

            for item in payload.get("products", []):
                prod = ReferenceProduct.from_dict(item)
                self.register(prod)

            logger.info("ProductRegistry loaded %d reference products from %s", len(self._all_products), target_path)
        except Exception as exc:
            logger.error("Failed to load ProductRegistry from %s: %s", target_path, exc)

    def register(self, product: ReferenceProduct) -> None:
        """Register a reference product into the index."""
        norm_gtin = _normalize_gtin(product.gtin)
        if norm_gtin:
            self._by_gtin[norm_gtin] = product
        self._all_products.append(product)

    def get_by_gtin(self, gtin: Optional[str]) -> Optional[ReferenceProduct]:
        """Look up reference product by barcode/GTIN (Tier 1 lookup)."""
        norm_gtin = _normalize_gtin(gtin)
        if not norm_gtin:
            return None
        return self._by_gtin.get(norm_gtin)

    def get_all(self) -> List[ReferenceProduct]:
        """Return all registered reference products."""
        return list(self._all_products)

    def count(self) -> int:
        return len(self._all_products)


# Global singleton instance for application use
_default_registry: Optional[ProductRegistry] = None


def get_product_registry() -> ProductRegistry:
    """Return singleton ProductRegistry instance."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ProductRegistry()
    return _default_registry
