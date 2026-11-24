"""Redis dedup keys for idempotent consumers.

done:{case}:{round}  — this round's pipeline finished; any later copy of the message is acked and dropped.
lock:{case}:{round}  — a worker is processing it right now; a concurrent copy backs off instead of
                       redoing the expensive extraction. TTL bounds how long a crashed worker blocks it.
These are an optimisation layer and a work-saver. Correctness of state lives in DynamoDB's
conditional writes; the tests turn each layer off separately to show what each one buys.
"""
from __future__ import annotations

import functools
import os

import redis

from .config import settings

DONE_TTL = 7 * 24 * 3600
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


@functools.lru_cache(maxsize=None)
def _r(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def r() -> redis.Redis:
    return _r(settings().redis_url)


def _on() -> bool:
    return not settings().unsafe_no_dedup


# @learn:dedup
def is_done(case_id: str, round_no: int) -> bool:
    return _on() and r().exists(f"done:{case_id}:{round_no}") == 1


def acquire(case_id: str, round_no: int, owner: str) -> bool:
    if not _on():
        return True
    ttl = int(os.environ.get("DOCVERIFY_LOCK_TTL", "30"))
    return bool(r().set(f"lock:{case_id}:{round_no}", owner, nx=True, ex=ttl))


def release(case_id: str, round_no: int, owner: str) -> None:
    if _on():
        r().eval(_RELEASE, 1, f"lock:{case_id}:{round_no}", owner)


def mark_done(case_id: str, round_no: int) -> None:
    if _on():
        r().set(f"done:{case_id}:{round_no}", "1", ex=DONE_TTL)
# @learn:end dedup


def singleton(name: str, ttl: int) -> bool:
    """At most one worker runs a periodic job per `ttl` seconds."""
    return bool(r().set(f"job:{name}", "1", nx=True, ex=ttl))
