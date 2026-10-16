#!/usr/bin/env python3
"""Add the validated zero-step warm trial and sparse status-1 trace."""
from __future__ import annotations


def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return text.replace(old, new, 1)


def add_valid_zero_step_warm_trial(source: str) -> str:
    """Run the existing zero-alpha trial only for NO_FEASIBLE_STEP at retry 0."""
    if "rain_warm_retry.eq.0 .and. rain_warm_search_status.eq.1" in source:
        raise ValueError("valid zero-step warm trial guard already present")
    return _once(
        source,
        "              if (rain_warm_alpha.le.0.0) exit\n",
        "              if (rain_warm_alpha.le.0.0 .and. &\n"
        "                  .not.(rain_warm_retry.eq.0 .and. rain_warm_search_status.eq.1)) exit\n",
        "warm zero-step loop guard",
    )


def add_status1_warm_trace(source: str) -> str:
    """Enable the existing warm budget row only for status-1 searches."""
    cold_guard = "            if (.false.) then\n            write(pr85_cold_unit,'"
    warm_guard = "            if (.false.) then\n            write(pr85_warm_unit,'"
    if source.count(cold_guard) != 1 or source.count(warm_guard) != 1:
        raise ValueError("expected one disabled cold and warm budget writer")
    if "PR87 NO_POSITIVE_WARM_STEP trace" in source:
        raise ValueError("status-1 warm trace already enabled")
    return source.replace(
        warm_guard,
        "            ! Sparse PR87 NO_POSITIVE_WARM_STEP trace: status 1 only.\n"
        "            if (rain_warm_search_status.eq.1) then\n"
        "            write(pr85_warm_unit,'",
        1,
    )


def add_rain_process_contract(source: str) -> str:
    """Add the zero-step control fix and sparse status-1 warm trace.

    Warm process admission retains its original consumer-pair-only domain.
    The later completed-state rain PSD gates remain separate.
    """
    source = add_valid_zero_step_warm_trial(source)
    return add_status1_warm_trace(source)
