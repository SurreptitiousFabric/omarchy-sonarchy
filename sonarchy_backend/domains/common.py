from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    """Process-owned request facts that clients cannot provide or replace."""

    backend_revision: int = 0
    mutation_started_callback: Callable[[], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def mark_mutation_started(self) -> None:
        if self.mutation_started_callback is not None:
            self.mutation_started_callback()


@dataclass(frozen=True)
class DomainService:
    handlers: dict[str, Callable[[dict[str, Any]], Any]]
    mutates: bool = True
    conditional_mutation: bool = False
    contextual_handlers: dict[str, Callable[[dict[str, Any], RequestContext], Any]] = field(
        default_factory=dict
    )

    @property
    def operations(self) -> frozenset[str]:
        return frozenset(self.handlers) | frozenset(self.contextual_handlers)

    def execute(
        self,
        operation: str,
        args: dict[str, Any],
        context: RequestContext | None = None,
    ) -> Any:
        handler = self.handlers.get(operation)
        if handler is not None:
            return handler(args)
        contextual_handler = self.contextual_handlers.get(operation)
        if contextual_handler is not None:
            return contextual_handler(args, context or RequestContext())
        raise KeyError(operation)


def clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "NOT_IMPLEMENTED" else text


def safe_call(call: Callable[[], Any], fallback: Any) -> Any:
    try:
        return call()
    except Exception:  # noqa: BLE001 - optional Sonos properties fail inconsistently
        return fallback


def safe_index(raw: Any, fallback: int = -1) -> int:
    try:
        return int(raw)
    except TypeError, ValueError:
        return fallback


def coordinator_for(speaker: Any) -> Any:
    def resolve() -> Any:
        group = speaker.group
        return getattr(group, "coordinator", None) or speaker

    return safe_call(resolve, speaker)


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
