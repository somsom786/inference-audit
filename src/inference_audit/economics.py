"""Conditional single-worker economics, kept separate from measurements."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Assumptions:
    usd_per_gpu_hour: float
    productive_fraction: float
    peak_rps: float
    headroom: float
    reserve_workers: int
    worker_count: int = 1
    billing_minutes: int = 60
    provisioned_hours: float = 730


def estimate(
    assumptions: Assumptions,
    output_tps: float | None,
    valid_rps: float,
    goodput_rps: float,
    qualified_arrival_rps: float | None,
) -> dict[str, float | int | str | None]:
    a = assumptions
    vals = (*vars(a).values(), valid_rps, goodput_rps)
    if (
        any(type(v) not in (int, float) or not 0 <= v <= 1e9 for v in vals)
        or (output_tps is not None and (type(output_tps) not in (int, float) or not 0 <= output_tps <= 1e9))
        or any(type(v) is not int for v in (a.reserve_workers, a.worker_count, a.billing_minutes))
        or goodput_rps > valid_rps
        or not 0 < a.productive_fraction <= 1
        or not 0 <= a.headroom < 1
        or a.billing_minutes < 1
        or a.worker_count < 1
        or (
            qualified_arrival_rps is not None
            and (type(qualified_arrival_rps) not in (float, int) or not 0 <= qualified_arrival_rps <= 1e9)
        )
    ):
        raise ValueError("Invalid cost or capacity inputs.")
    seconds = 3600 * a.productive_fraction
    capacity = qualified_arrival_rps * (1 - a.headroom) if qualified_arrival_rps is not None else None
    needed = math.ceil(a.peak_rps / capacity) + a.reserve_workers if capacity else None
    baseline = (
        math.ceil(a.provisioned_hours * 60 / a.billing_minutes) * a.billing_minutes / 60 * a.usd_per_gpu_hour
    )
    return {
        "classification": "conditional estimate, assumes independent workers and workload parity",
        "gpu_hours_per_million_tokens": 1e6 / (seconds * output_tps) if output_tps else None,
        "usd_per_million_tokens": a.usd_per_gpu_hour * 1e6 / (seconds * output_tps) if output_tps else None,
        "usd_per_successful": a.usd_per_gpu_hour / (seconds * valid_rps) if valid_rps else None,
        "usd_per_on_time": a.usd_per_gpu_hour / (seconds * goodput_rps) if goodput_rps else None,
        "planning_rps_per_worker": capacity,
        "conditional_workers": needed,
        "current_provisioned_usd": baseline * a.worker_count,
        "conditional_provisioned_usd": baseline * needed if needed is not None else None,
        "conditional_savings_usd": baseline * (a.worker_count - needed) if needed is not None else None,
        "provisioned_usd_for_reserve_workers": baseline * a.reserve_workers,
        "verified_savings_usd": None,
        "break_even_peak_rps_for_current_workers": capacity * max(0, a.worker_count - a.reserve_workers)
        if capacity is not None
        else None,
    }
