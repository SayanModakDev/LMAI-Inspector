"""
LMAI Inspector Automated Accuracy Benchmark & Evaluation Framework.
Provides evaluation schemas, normalizers, metrics calculators, test runners, and reporting.
"""

import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from .schema import (
    BenchmarkCase,
    BenchmarkDataset,
    ExpectedContext,
    ExpectedDeclaration,
)
from .evaluator import BenchmarkEvaluator
from .metrics import BenchmarkMetricsCalculator


__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "ExpectedContext",
    "ExpectedDeclaration",
    "BenchmarkEvaluator",
    "BenchmarkMetricsCalculator",
]
