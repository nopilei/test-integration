import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeAlias

logger = logging.getLogger(__name__)

CheckFn: TypeAlias = Callable[[], Awaitable[bool] | bool]


@dataclass
class Probe:
    name: str
    check: CheckFn
    critical_for_readiness: bool = True
    succeeded_once: bool = False
    last_ok: bool = False
    last_checked_at: float = 0.0


@dataclass
class ProbeRegistry:
    liveness_flag: bool = True
    probes: list[Probe] = field(default_factory=list)

    def add(self, name: str, check: CheckFn, critical: bool = True) -> None:
        self.probes.append(Probe(name=name, check=check, critical_for_readiness=critical))

    def mark_dead(self, reason: str) -> None:
        logger.error("Liveness marked dead: %s", reason)
        self.liveness_flag = False

    async def check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for probe in self.probes:
            ok = await _run_check(probe)
            probe.last_ok = ok
            probe.last_checked_at = time.time()
            if ok:
                probe.succeeded_once = True
            results[probe.name] = ok
        return results

    async def is_ready(self) -> bool:
        results = await self.check_all()
        return all(
            results[p.name]
            for p in self.probes
            if p.critical_for_readiness
        )

    async def has_started(self) -> bool:
        await self.check_all()
        return all(
            p.succeeded_once
            for p in self.probes
            if p.critical_for_readiness
        )

    def is_alive(self) -> bool:
        return self.liveness_flag


async def _run_check(probe: Probe) -> bool:
    try:
        result = probe.check()
        if asyncio.iscoroutine(result):
            result = await result
        return bool(result)
    except Exception:
        logger.exception("Probe %r raised", probe.name)
        return False
