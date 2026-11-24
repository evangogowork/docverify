"""Reviewer routing: a min-heap over (enqueued_at - risk * AGING), with lazy deletion.

Priority = risk * AGING + seconds waited. Every waiting case gains one point per second, so the
ordering between two cases never changes over time — which means the heap key can be computed once,
at push time: argmax(risk*K + now - t) == argmin(t - risk*K). A high-risk case jumps the queue;
a low-risk case that has waited long enough still gets reviewed.
"""
from __future__ import annotations

import heapq
import threading
import time

AGING_SECONDS_PER_RISK_POINT = 60.0


# @learn:review-heap
class ReviewQueue:
    def __init__(self, aging: float = AGING_SECONDS_PER_RISK_POINT):
        self.aging = aging
        self._heap: list[tuple[float, str]] = []
        self._live: dict[str, float] = {}
        self._lock = threading.Lock()

    def key(self, risk: float, enqueued_at: float) -> float:
        return enqueued_at - risk * self.aging

    def push(self, case_id: str, risk: float, enqueued_at: float) -> None:
        k = self.key(risk, enqueued_at)
        with self._lock:
            if self._live.get(case_id) == k:
                return
            self._live[case_id] = k
            heapq.heappush(self._heap, (k, case_id))

    def remove(self, case_id: str) -> None:
        with self._lock:
            self._live.pop(case_id, None)    # the heap entry is skipped when it surfaces

    def pop(self) -> str | None:
        with self._lock:
            while self._heap:
                k, cid = heapq.heappop(self._heap)
                if self._live.get(cid) == k:
                    del self._live[cid]
                    return cid
            return None

    def peek_order(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        with self._lock:
            items = sorted((k, c) for c, k in self._live.items())
        return [{"case_id": c, "priority": round(now - k, 1)} for k, c in items]

    def __len__(self) -> int:
        return len(self._live)
# @learn:end review-heap
