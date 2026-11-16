import asyncio
from datetime import datetime

from clinic_voice_agent.limits import calls_today, hang_up_after

NOW = datetime(2026, 11, 15, 16, 0)


def test_only_todays_records_count_toward_the_cap(tmp_path):
    for name in ("2026-11-15T100000-test-a", "2026-11-15T153000-console", "2026-11-14T235959-x"):
        (tmp_path / f"{name}.json").write_text("{}")
    (tmp_path / "2026-11-15T120000-note.txt").write_text("not a record")
    assert calls_today(tmp_path, NOW) == 2


def test_a_missing_recordings_folder_means_no_calls_yet(tmp_path):
    assert calls_today(tmp_path / "nothing-here", NOW) == 0


async def test_the_call_is_ended_after_the_limit_with_a_goodbye_first():
    events = []

    async def goodbye():
        events.append("goodbye")

    await hang_up_after(0.01, goodbye, lambda: events.append("hang up"))
    assert events == ["goodbye", "hang up"]


async def test_the_line_is_closed_even_when_the_goodbye_fails():
    events = []

    async def broken():
        raise RuntimeError("no voice")

    try:
        await hang_up_after(0.01, broken, lambda: events.append("hang up"))
    except RuntimeError:
        pass
    assert events == ["hang up"]


async def test_a_call_that_ends_sooner_cancels_the_timer_and_nothing_is_said():
    events = []

    async def goodbye():
        events.append("goodbye")

    task = asyncio.create_task(hang_up_after(5, goodbye, lambda: events.append("hang up")))
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert events == []


def test_a_worker_reads_as_full_exactly_when_every_allowed_call_is_running():
    from clinic_voice_agent.limits import concurrency_load

    assert concurrency_load(0, 1) == 0.0 and concurrency_load(1, 1) == 1.0
    assert concurrency_load(1, 2) == 0.5 and concurrency_load(2, 2) == 1.0
    # the framework's production threshold is 0.7: below it a worker takes calls, above it not
    assert concurrency_load(1, 2) < 0.7 <= concurrency_load(2, 2)
