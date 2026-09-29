"""Live mode: run the real graph on one invoice, streaming each step as it finishes."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import streamlit as st

from opsmesh.agents.graph import build_graph, graph_state, resume_run
from opsmesh.agents.llm import model_name
from opsmesh.config import DATA_DIR
from opsmesh.replay.store import build_replay

UPLOAD_DIR = DATA_DIR / "runtime" / "uploads"


def max_runs() -> int:
    return int(os.getenv("LIVE_MAX_RUNS", "5"))


def runs_left() -> int:
    return max(0, max_runs() - len(st.session_state.get("live_runs", {})))


def _graph():
    if "live_graph" not in st.session_state:
        st.session_state.live_graph = build_graph()  # in-memory checkpointer, this session only
    return st.session_state.live_graph


def next_live_id() -> str:
    return f"LIVE-{len(st.session_state.get('live_runs', {})) + 1:04d}"


def save_upload(doc_id: str, data: bytes) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    path.write_bytes(data)
    return path


def stream_run(doc_id: str, pdf: Path, received_date: str | None) -> Iterator[dict]:
    """Yields each step log as its node finishes; stores the replay when done or paused."""
    graph = _graph()
    config = {"configurable": {"thread_id": doc_id}}
    inputs = {"doc_id": doc_id, "pdf_path": str(pdf), "received_date": received_date, "errors": [], "steps": []}
    for update in graph.stream(inputs, config, stream_mode="updates"):
        for node, delta in update.items():
            if node == "__interrupt__" or not isinstance(delta, dict):
                continue
            for step in delta.get("steps") or []:
                yield step
    _store(doc_id, pdf)


def resume_live(doc_id: str, decision: dict) -> dict:
    resume_run(_graph(), doc_id, decision)
    return _store(doc_id, Path(st.session_state.live_runs[doc_id]["pdf_path"]))


def _store(doc_id: str, pdf: Path) -> dict:
    state = graph_state(_graph(), doc_id)
    replay = build_replay(state, file=pdf.name, model=model_name()) | {"pdf_path": str(pdf), "live": True}
    st.session_state.setdefault("live_runs", {})[doc_id] = replay
    return replay
