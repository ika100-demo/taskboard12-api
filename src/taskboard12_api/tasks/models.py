"""Task models."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, StringConstraints, field_validator

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    due_date: date | None = None

    @field_validator("due_date", mode="before")
    @classmethod
    def _check_due_date(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
            raise ValueError("due_date must be a date in YYYY-MM-DD form")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("due_date must be a valid calendar date") from exc


class Task(BaseModel):
    id: str
    title: str
    due_date: date | None
    created_at: datetime
