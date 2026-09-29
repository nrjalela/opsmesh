"""Replay files: one JSON per invoice run, recorded once, watched for free."""

from __future__ import annotations

import json
from pathlib import Path

from opsmesh.agents.steps import StepLog, now_iso
from opsmesh.config import REPLAY_DIR

SUMMARY_FILE = "_summary.json"


def status_of(state: dict) -> str:
    if state.get("pending"):
        return "awaiting_approval"
    outcome = state.get("outcome") or {}
    return outcome.get("status", "error")


def build_replay(state: dict, *, file: str, model: str, recorded_at: str | None = None) -> dict:
    steps = state.get("steps", [])
    return {
        "doc_id": state["doc_id"],
        "file": file,
        "received_date": state.get("received_date"),
        "recorded_at": recorded_at or now_iso(),
        "model": model,
        "status": status_of(state),
        "state": {k: state.get(k) for k in ("extraction", "validation", "invoice", "match", "analysis",
                                            "draft_requests", "route", "decision", "outcome", "errors")},
        "pending": state.get("pending"),
        "steps": steps,
        "metrics": {
            "automated_ms": sum(s["duration_ms"] for s in steps if s["kind"] != "human"),
            "llm_ms": sum(s["duration_ms"] for s in steps if s["kind"] == "llm"),
            "cost_usd": round(sum(s.get("cost_usd", 0) for s in steps), 6),
            "input_tokens": sum(s.get("input_tokens", 0) for s in steps),
            "output_tokens": sum(s.get("output_tokens", 0) for s in steps),
        },
    }


def save_replay(replay: dict, folder: Path = REPLAY_DIR) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{replay['doc_id']}.json"
    path.write_text(json.dumps(replay, indent=2) + "\n")
    return path


def load_replays(folder: Path = REPLAY_DIR) -> dict[str, dict]:
    if not folder.exists():
        return {}
    return {p.stem: json.loads(p.read_text()) for p in sorted(folder.glob("OPS-*.json"))}


def load_summary(folder: Path = REPLAY_DIR) -> dict | None:
    p = folder / SUMMARY_FILE
    return json.loads(p.read_text()) if p.exists() else None


def apply_decision(replay: dict, decision: dict) -> dict:
    """Finish a paused replay with a visitor's decision, using the same code the live
    graph runs after an interrupt. Returns a new replay; the file on disk is untouched."""
    from opsmesh.agents.graph import finalise  # local import: graph pulls in the SDK

    state = {**replay["state"], "doc_id": replay["doc_id"], "decision": decision}
    human = StepLog(node="human_review", title="Human approval", kind="human", started_at=now_iso(), duration_ms=0,
                    summary=f"{'Approved' if decision['decision'] == 'approve' else 'Rejected'} by "
                            f"{decision.get('reviewer') or state['route']['approver']}."
                            + (f' "{decision["note"]}"' if decision.get("note") else ""),
                    reasoning=decision.get("note") or "").model_dump(mode="json")
    result = finalise(state, "post" if decision["decision"] == "approve" else "reject")
    new_state = {**replay["state"], "decision": decision, "outcome": result["outcome"]}
    return {**replay, "state": new_state, "pending": None, "status": result["outcome"]["status"],
            "steps": replay["steps"] + [human] + result["steps"]}
