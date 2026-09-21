"""Shared fixtures for Freeze R2 contract tests."""

from __future__ import annotations

import pytest

from validation.v2_phase6_r2.reconcile import build_reconciliation_report


@pytest.fixture(scope="session")
def reconciliation_report():
    return build_reconciliation_report()
