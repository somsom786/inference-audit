"""Optional NVIDIA board telemetry. Missing data remains missing."""

import asyncio
import csv
from dataclasses import dataclass
import shutil
import time
from typing import Any, Protocol

FIELDS = (
    "name",
    "driver_version",
    "memory.total",
    "memory.used",
    "memory.free",
    "utilization.gpu",
    "temperature.gpu",
    "clocks.sm",
    "clocks.mem",
    "power.draw",
    "clocks_event_reasons.hw_thermal_slowdown",
    "clocks_event_reasons.sw_thermal_slowdown",
    "compute_cap",
    "clocks_event_reasons.sw_power_cap",
)
KEYS = (
    "gpu",
    "driver",
    "total_mib",
    "used_mib",
    "free_mib",
    "busy_pct",
    "temp_c",
    "sm_mhz",
    "mem_mhz",
    "power_w",
    "hw_thermal",
    "sw_thermal",
    "compute_capability",
    "power_cap_active",
)


class Telemetry(Protocol):
    async def sample(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Nvidia:
    index: int

    async def sample(self) -> dict[str, Any]:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return {"state": "unavailable", "reason": "nvidia-smi not installed"}
        proc = await asyncio.create_subprocess_exec(
            exe,
            "-i",
            str(self.index),
            "--query-gpu=" + ",".join(FIELDS),
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(4):
                output, _ = await proc.communicate()
        except (TimeoutError, asyncio.CancelledError):
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
            raise
        if proc.returncode:
            return {"state": "unavailable", "reason": "nvidia-smi returned an error"}
        cells = list(csv.reader(output.decode(errors="replace").splitlines(), skipinitialspace=True))
        if len(cells) != 1 or len(cells[0]) != len(KEYS):
            return {"state": "unavailable", "reason": "malformed board data"}
        row: dict[str, Any] = {"state": "ok", "t": time.monotonic()}
        for index, (k, value) in enumerate(zip(KEYS, cells[0], strict=True)):
            if index in (0, 1, 10, 11, 12, 13):
                row[k] = value
            else:
                try:
                    row[k] = float(value)
                except ValueError:
                    row[k] = None
        return row
