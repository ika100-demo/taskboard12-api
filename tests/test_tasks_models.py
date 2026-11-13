"""Unit tests for the TaskCreate model."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from taskboard12_api.tasks.models import TaskCreate


def test_title_is_trimmed() -> None:
    assert TaskCreate(title="  hello  ").title == "hello"


@pytest.mark.parametrize("title", ["", "   ", "\t\n"])
def test_blank_title_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title=title)


def test_title_length_limits() -> None:
    assert TaskCreate(title="a").title == "a"
    assert len(TaskCreate(title="a" * 200).title) == 200
    with pytest.raises(ValidationError):
        TaskCreate(title="a" * 201)


def test_title_trimmed_before_length_check() -> None:
    assert len(TaskCreate(title=" " + "a" * 200 + " ").title) == 200


def test_title_missing_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({})


def test_due_date_defaults_to_none() -> None:
    assert TaskCreate(title="x").due_date is None


def test_due_date_none() -> None:
    assert TaskCreate(title="x", due_date=None).due_date is None


def test_due_date_valid_string() -> None:
    assert TaskCreate(title="x", due_date="2030-02-28").due_date == date(2030, 2, 28)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    ["2030-02-30", "2030-13-01", "2030-1-1", "30-01-2030", "tomorrow", "", "2030-01-01T00:00:00"],
)
def test_due_date_invalid_strings_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "x", "due_date": value})


@pytest.mark.parametrize("value", [20300101, 1.5, True, [], {}, date(2030, 1, 1)])
def test_due_date_non_string_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "x", "due_date": value})
