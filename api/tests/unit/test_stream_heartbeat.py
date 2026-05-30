"""Unit tests for the streaming keepalive (`_pump`).

The collect stream emits a heartbeat while a long stage runs so idle proxies /
load balancers don't drop the connection mid-analysis. These tests prove a slow
stage produces heartbeats (and still yields its result) while a fast one does not.
"""

from __future__ import annotations

import asyncio
import json

from app.api.v1 import reviews as reviews_mod


async def test_pump_emits_heartbeats_for_slow_work_and_returns_value(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(reviews_mod, "_HEARTBEAT_SECONDS", 0.02)

    async def slow() -> str:
        await asyncio.sleep(0.12)
        return "done-value"

    holder: dict[str, object] = {}
    events = [ev async for ev in reviews_mod._pump(slow(), holder)]

    assert events, "a slow stage should emit at least one heartbeat"
    for raw in events:
        assert json.loads(raw.decode()) == {"type": "heartbeat"}
    assert holder["value"] == "done-value"


async def test_pump_fast_work_emits_no_heartbeat(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(reviews_mod, "_HEARTBEAT_SECONDS", 5.0)

    async def fast() -> int:
        return 42

    holder: dict[str, object] = {}
    events = [ev async for ev in reviews_mod._pump(fast(), holder)]

    assert events == []
    assert holder["value"] == 42
