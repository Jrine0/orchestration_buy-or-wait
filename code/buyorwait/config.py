"""Paths and engine settings. Paths resolve lazily so importing never touches dataset/."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CODE_DIR.parent


def dataset_dir() -> Path:
    return Path(os.environ.get("BOW_DATASET_DIR", REPO_ROOT / "dataset"))


def output_path() -> Path:
    return Path(os.environ.get("BOW_OUTPUT", REPO_ROOT / "output.csv"))


def load_env_files() -> list[str]:
    """Read KEY=VALUE lines from .env / .env.local (repo root or code/). Secrets stay in env vars only.
    Values in these files override the inherited shell so a stale exported key cannot shadow them."""
    loaded = []
    for base in (REPO_ROOT, CODE_DIR):
        for name in (".env", ".env.local"):
            p = base / name
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export ").strip()
                os.environ[k] = v.strip().strip('"').strip("'")
                loaded.append(k)
    return loaded


CASE_DIR = CODE_DIR / "case_files"
EVAL_DIR = CODE_DIR / "evaluation"
PROMPT_DIR = CODE_DIR / "prompts"
CACHE_DIR = CODE_DIR / "cache"


@dataclass(frozen=True)
class Settings:
    # R6 window: request_date..request_date+86. The solved rows bound the reference forecast's last
    # included day to +84..+86 (request_10 counts spending on +84; request_05 and request_10 omit rent
    # on +88 and +87; request_09 omits rent on +90). +86 is the widest window consistent with that.
    horizon_days: int = 87
    min_occurrences: int = 3        # R34: recurrence gate
    variable_amount: str = "mean"   # projection for variable-amount series: mean | max | last | recent_mean
    recent_window: int = 3
    pending_debit_on: str = "settlement"  # when a pending debit leaves the balance: settlement | request
    same_day_debits_first: bool = False   # salary posts at start of day; payday bills and payments follow it
    variable_spend_before_credit: bool = False  # every-k-days spending on payday happens before the salary posts
    include_request_day_flows: bool = True  # balance on request_date already reflects that day's activity


SETTINGS = Settings()
