from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sonarchy_mcp_contract import (
    MCP_BACKEND_FIELDS,
    MCP_OPERATION_PLAY_EXECUTE,
    MCP_OPERATION_PLAY_VALIDATE,
)

from ..contracts import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_PROTOCOL_REQUEST_ID_BYTES,
    protocol_line,
    result_payload,
)
from .apple_playlist_plan import PLAN_TICKET_TTL_SEC, PlanTicketStore
from .common import DomainService, RequestContext, string_arg
from .errors import PlanConflictError
from .media import validate_playlist_id
from .playlist_playback import PLAYLIST_PLAY_SIDE_EFFECTS
from .ports import PlaylistPlayPlansPort


@dataclass(frozen=True)
class PlaylistPlayPlan:
    operation: str
    room_uid: str
    playlist_id: str
    target_state: dict[str, Any]
    plan_fingerprint: str

    def backend_value(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "roomUid": self.room_uid,
            "playlistId": self.playlist_id,
            "targetState": copy.deepcopy(self.target_state),
            "planFingerprint": self.plan_fingerprint,
        }


def _plan_fingerprint(*, room_uid: str, playlist_id: str, target_state: dict[str, Any]) -> str:
    binding = {
        "operation": MCP_OPERATION_PLAY_EXECUTE,
        "roomUid": room_uid,
        "playlistId": playlist_id,
        "targetState": target_state,
        "expectedSideEffects": PLAYLIST_PLAY_SIDE_EFFECTS,
    }
    encoded = json.dumps(binding, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PlaylistPlayPlanService:
    def __init__(
        self,
        backend: PlaylistPlayPlansPort,
        *,
        tickets: PlanTicketStore,
    ) -> None:
        self.backend = backend
        self.tickets = tickets

    def services(self) -> tuple[DomainService, DomainService]:
        validate = DomainService(
            {},
            mutates=False,
            contextual_handlers={MCP_OPERATION_PLAY_VALIDATE: self.validate},
        )
        execute = DomainService(
            {},
            conditional_mutation=True,
            contextual_handlers={MCP_OPERATION_PLAY_EXECUTE: self.execute},
        )
        return validate, execute

    def validate(self, args: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        if not MCP_BACKEND_FIELDS[MCP_OPERATION_PLAY_VALIDATE].accepts(args):
            raise ValueError("Playlist playback preflight accepts only roomUid and playlistId")
        room_uid = string_arg(args, "roomUid").strip()
        playlist_id = validate_playlist_id(string_arg(args, "playlistId"))
        target_state = self.backend.inspect_playlist_play_target(room_uid, playlist_id)
        fingerprint = _plan_fingerprint(
            room_uid=room_uid,
            playlist_id=playlist_id,
            target_state=target_state,
        )
        plan = PlaylistPlayPlan(
            operation=MCP_OPERATION_PLAY_EXECUTE,
            room_uid=room_uid,
            playlist_id=playlist_id,
            target_state=copy.deepcopy(target_state),
            plan_fingerprint=fingerprint,
        )
        ticket = self.tickets.issue(plan)
        review = {
            "ok": True,
            "operation": plan.operation,
            "planToken": ticket.token,
            "planFingerprint": f"sha256:{fingerprint}",
            "expiresAtEpochMs": ticket.expires_epoch_ms,
            "expiresInSec": PLAN_TICKET_TTL_SEC,
            "approvalRequired": True,
            "room": copy.deepcopy(target_state["room"]),
            "topology": copy.deepcopy(target_state["topology"]),
            "playlist": copy.deepcopy(target_state["playlist"]),
            "queue": copy.deepcopy(target_state["queue"]),
            "expectedSideEffects": list(PLAYLIST_PLAY_SIDE_EFFECTS),
        }
        worst_case_request_id = "\\" * MAX_PROTOCOL_REQUEST_ID_BYTES
        envelope = result_payload(
            worst_case_request_id,
            revision=context.backend_revision,
            value=review,
        )
        if len(protocol_line(envelope).encode("utf-8")) > MAX_PROTOCOL_LINE_BYTES:
            self.tickets.cancel_unpublished(ticket.token)
            raise ValueError("The playlist playback review is too large for the protocol")
        return review

    def execute(self, args: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        if not MCP_BACKEND_FIELDS[MCP_OPERATION_PLAY_EXECUTE].accepts(args):
            raise ValueError("Execution accepts only planToken and approved")
        if args.get("approved") is not True:
            raise ValueError("Explicit approval is required immediately before execution")
        plan = self.tickets.claim(args.get("planToken"))
        if not isinstance(plan, PlaylistPlayPlan) or plan.operation != MCP_OPERATION_PLAY_EXECUTE:
            raise PlanConflictError("The plan token is bound to another operation")
        return self.backend.execute_preflighted_playlist_play(
            plan.backend_value(),
            mutation_started_callback=context.mark_mutation_started,
        )
