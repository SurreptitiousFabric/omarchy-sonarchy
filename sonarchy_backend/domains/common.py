from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainService:
    handlers: dict[str, Callable[[dict[str, Any]], Any]]
    mutates: bool = True

    @property
    def operations(self) -> frozenset[str]:
        return frozenset(self.handlers)

    def execute(self, operation: str, args: dict[str, Any]) -> Any:
        handler = self.handlers.get(operation)
        if handler is None:
            raise KeyError(operation)
        return handler(args)


def string_arg(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def number_arg(args: dict[str, Any], name: str) -> int | float:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def bool_arg(args: dict[str, Any], name: str) -> bool:
    value = args.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def string_list_arg(args: dict[str, Any], name: str) -> list[str]:
    value = args.get(name)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must not contain duplicates")
    return value
