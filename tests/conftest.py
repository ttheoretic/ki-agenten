import asyncio
import os

import pytest

os.environ.pop("OPENAI_API_KEY", None)
os.environ["AICO_MODE"] = "dry_run"

from aicompany.company import Company  # noqa: E402
from aicompany.config import load_settings  # noqa: E402
from aicompany.llm.mock import MockBackend  # noqa: E402
from aicompany.orchestrator import Orchestrator  # noqa: E402


def deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = deep_merge(out.get(k, {}), v) if isinstance(v, dict) else v
    return out


@pytest.fixture
def make_company(tmp_path):
    def factory(backend=None, data_dir=None, **overrides):
        base = {"orchestrator": {"retry_backoff_seconds": 0.0}}
        settings = load_settings(mode="dry_run", data_dir=data_dir or tmp_path / "data", overrides=deep_merge(base, overrides))
        return Company(settings, backend=backend or MockBackend())
    return factory


@pytest.fixture
def company(make_company):
    return make_company()


def run(company, n=1):
    out = None
    for _ in range(n):
        out = asyncio.run(Orchestrator(company).run_once("test"))
    return out


def run_until_finished(company, max_runs=12):
    summaries = []
    for _ in range(max_runs):
        s = run(company)
        summaries.append(s)
        if company.db.get_meta("experiment_status") == "finished" or s.status != "completed":
            break
    return summaries
