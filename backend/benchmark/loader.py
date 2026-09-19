"""
Dataset loader and validator for LMAI Inspector benchmark suites.
Handles path resolution, schema validation, and tag/case filtering.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import ValidationError

from .schema import BenchmarkCase, BenchmarkDataset

logger = logging.getLogger(__name__)


class BenchmarkDatasetError(Exception):
    """Raised when benchmark dataset loading or validation fails."""
    pass


def load_benchmark_dataset(
    dataset_path_or_dict: Union[str, Path, Dict[str, Any]],
    tags: Optional[Union[str, List[str], Set[str]]] = None,
    case_ids: Optional[Union[str, List[str], Set[str]]] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> BenchmarkDataset:
    """
    Load and validate a benchmark dataset from a JSON file path or dictionary.

    Args:
        dataset_path_or_dict: Path to dataset JSON file or pre-parsed dict.
        tags: Optional filter for tags (case will be included if it matches any tag).
        case_ids: Optional filter for specific case_ids.
        base_dir: Base directory for resolving relative image paths.

    Returns:
        Validated BenchmarkDataset with filtered cases.
    """
    raw_data: Dict[str, Any] = {}
    origin_dir = Path(base_dir) if base_dir else Path.cwd()

    if isinstance(dataset_path_or_dict, (str, Path)):
        file_path = Path(dataset_path_or_dict)
        if not file_path.exists():
            raise BenchmarkDatasetError(f"Benchmark dataset file not found: {file_path.resolve()}")
        origin_dir = file_path.parent
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                raw_data = json.load(handle)
        except json.JSONDecodeError as jde:
            raise BenchmarkDatasetError(
                f"Failed to parse JSON in benchmark dataset {file_path}: {jde.msg} (line {jde.lineno}, col {jde.colno})"
            ) from jde
        except Exception as exc:
            raise BenchmarkDatasetError(f"Error reading benchmark dataset {file_path}: {exc}") from exc
    elif isinstance(dataset_path_or_dict, dict):
        raw_data = dataset_path_or_dict
    else:
        raise BenchmarkDatasetError(f"Unsupported dataset input type: {type(dataset_path_or_dict)}")

    # Pydantic schema validation
    try:
        dataset = BenchmarkDataset.model_validate(raw_data)
    except ValidationError as val_err:
        error_lines = []
        for err in val_err.errors():
            loc = " -> ".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "invalid")
            error_lines.append(f"  - [{loc}]: {msg}")
        detailed_msg = "\n".join(error_lines)
        raise BenchmarkDatasetError(
            f"Benchmark dataset schema validation failed with {len(val_err.errors())} error(s):\n{detailed_msg}"
        ) from val_err

    # Normalize filter parameters
    filter_tags: Optional[Set[str]] = None
    if tags:
        if isinstance(tags, str):
            filter_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}
        else:
            filter_tags = {str(t).strip().lower() for t in tags if str(t).strip()}

    filter_case_ids: Optional[Set[str]] = None
    if case_ids:
        if isinstance(case_ids, str):
            filter_case_ids = {c.strip().upper() for c in case_ids.split(",") if c.strip()}
        else:
            filter_case_ids = {str(c).strip().upper() for c in case_ids if str(c).strip()}

    # Filter and resolve image paths
    filtered_cases: List[BenchmarkCase] = []
    for case in dataset.cases:
        # Case ID filtering
        if filter_case_ids and case.case_id.upper() not in filter_case_ids:
            continue

        # Tag filtering
        if filter_tags:
            case_tags = {t.strip().lower() for t in case.tags}
            if not case_tags.intersection(filter_tags):
                continue

        # Resolve image paths
        resolved_images: List[str] = []
        for img_rel in case.images:
            cand_path = Path(img_rel)
            if not cand_path.is_absolute():
                # Try relative to dataset file directory
                resolved = (origin_dir / cand_path).resolve()
                if not resolved.exists():
                    # Try relative to current working directory
                    resolved_cwd = (Path.cwd() / cand_path).resolve()
                    if resolved_cwd.exists():
                        resolved = resolved_cwd
                resolved_images.append(str(resolved))
            else:
                resolved_images.append(str(cand_path.resolve()))
        case.images = resolved_images

        filtered_cases.append(case)

    dataset.cases = filtered_cases
    logger.info(
        "Loaded benchmark dataset '%s' with %d cases (filtered from original %d)",
        dataset.dataset_name,
        len(dataset.cases),
        len(raw_data.get("cases", [])),
    )
    return dataset
