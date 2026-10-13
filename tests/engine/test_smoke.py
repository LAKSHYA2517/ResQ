import importlib
import re
from pathlib import Path

import pytest

SUBPACKAGES = ["world", "search", "logic", "uncertainty", "planning", "decision", "agent"]
ENGINE = Path(__file__).resolve().parents[2] / "engine" / "resq"
WEB_IMPORT = re.compile(r"^\s*(?:from|import)\s+(fastapi|starlette|uvicorn|pydantic|api)\b", re.M)


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    importlib.import_module(f"resq.{name}")


def test_engine_has_no_web_imports() -> None:
    offenders = [str(p) for p in ENGINE.rglob("*.py") if WEB_IMPORT.search(p.read_text())]
    assert offenders == []
