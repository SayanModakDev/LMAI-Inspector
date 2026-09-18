"""Reference Product Registry Package for LMAI Inspector."""

from app.registry.product_registry import (
    ProductRegistry,
    ReferenceProduct,
    get_product_registry,
)
from app.registry.matcher import (
    RegistryMatchResult,
    match_product,
    improve_candidate_ranking,
)

__all__ = [
    "ProductRegistry",
    "ReferenceProduct",
    "get_product_registry",
    "RegistryMatchResult",
    "match_product",
    "improve_candidate_ranking",
]
