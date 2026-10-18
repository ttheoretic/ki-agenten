import asyncio

from aicompany.scheduler import run_scheduler


def test_scheduler_is_bounded(company):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    n = asyncio.run(run_scheduler(company, interval_minutes=1, max_total_runs=3, max_runs_per_day=100, sleep=fake_sleep, log=lambda m: None))
    assert n == 3 and len(sleeps) == 2


def test_scheduler_stops_on_stop_flag(company):
    company.control.apply("stop_new", "owner")
    n = asyncio.run(run_scheduler(company, interval_minutes=1, max_total_runs=5, max_runs_per_day=5,
                                  sleep=lambda s: asyncio.sleep(0), log=lambda m: None))
    assert n == 0


def test_scheduler_daily_limit(company):
    async def fake_sleep(s):
        pass

    msgs = []
    n = asyncio.run(run_scheduler(company, interval_minutes=1, max_total_runs=1, max_runs_per_day=0, max_idle_cycles=3,
                                  sleep=fake_sleep, log=msgs.append))
    assert n == 0
    assert sum("Tageslimit" in m for m in msgs) == 3 and "Wartezyklen" in msgs[-1]
