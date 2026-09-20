"""Regression guards for health responsiveness and bounded scan execution."""

import inspect

import pytest
from fastapi import HTTPException

from app.api.scan import acquire_scan_slot, perform_scan
from app.main import health_check


def test_scan_pipeline_is_dispatched_as_sync_worker_work():
    assert inspect.iscoroutinefunction(perform_scan) is False
    assert inspect.iscoroutinefunction(health_check) is True


def test_scan_capacity_is_bounded_without_queueing_duplicate_work():
    active_slot = acquire_scan_slot()
    next(active_slot)
    try:
        blocked_slot = acquire_scan_slot()
        with pytest.raises(HTTPException) as exc_info:
            next(blocked_slot)
        assert exc_info.value.status_code == 429
        assert "active analysis" in exc_info.value.detail
    finally:
        active_slot.close()

    available_again = acquire_scan_slot()
    next(available_again)
    available_again.close()
