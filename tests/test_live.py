"""Live mode (GitHub issues) end to end, offline: real graph, real SQLite checkpoints,
real state files. Only the model and the PDF download are stubbed."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

import opsmesh.agents.graph as graph_mod
from opsmesh.config import DATA_DIR, INVOICE_DIR, load_tolerances
from opsmesh.engine.matching import match_invoice
from opsmesh.engine.models import InvoiceDocument
from opsmesh.live import issue as issue_mod
from opsmesh.live.issue import PDFError, check_pdf, find_pdf_url, is_allowed_redirect, parse_command
from opsmesh.live.runner import handle_comment, process_issue
from opsmesh.live.state import StateStore
from tests.fakes import extraction_from_truth, fake_exception_agent, fake_result

KEY = json.loads((DATA_DIR / "answer_key.json").read_text())
BY_SCENARIO = {v["scenario"]: d for d, v in KEY.items()}
NOW = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)  # 12:00 in Sydney
ATTACH = "https://github.com/user-attachments/files/123/{}.pdf"


def pdf_bytes(doc: str) -> bytes:
    return (INVOICE_DIR / f"{doc}.pdf").read_bytes()


def body_for(doc: str) -> str:
    return f"### Invoice PDF\n\n[{doc}.pdf]({ATTACH.format(doc)})\n\n### Confirm\n\n- [X] Synthetic"


@pytest.fixture
def llm(monkeypatch):
    """Stub Claude: answer from the answer key, keyed by the PDF's hash. Counts calls."""
    by_hash = {hashlib.sha256(pdf_bytes(d)).hexdigest(): KEY[d]["invoice"] for d in KEY}
    calls = {"intake": 0}

    def intake(path, received=None):
        calls["intake"] += 1
        return fake_result(extraction_from_truth(by_hash[hashlib.sha256(path.read_bytes()).hexdigest()]))

    monkeypatch.setattr(graph_mod, "run_intake", intake)
    monkeypatch.setattr(graph_mod, "run_exception_agent", fake_exception_agent)
    return calls


def fetch(url: str) -> bytes:
    return pdf_bytes(url.rsplit("/", 1)[1].removesuffix(".pdf"))


def submit(store, issue, doc, now=NOW, **kw):
    return process_issue(issue=issue, author="nrjalela", body=body_for(doc), created_at="2026-10-01T02:00:00Z",
                         store=store, now=now, fetch=fetch, **kw)


def comment(store, issue, text, doc="OPS-0001", now=NOW, author="nrjalela"):
    return handle_comment(issue=issue, author=author, comment_body=text, issue_body=body_for(doc),
                          created_at="2026-10-01T02:00:00Z", store=store, now=now, fetch=fetch)


# --- parsing and input checks ----------------------------------------------------------------

def test_finds_the_uploaded_pdf():
    assert find_pdf_url(body_for("OPS-0001")) == ATTACH.format("OPS-0001")
    raw = "https://raw.githubusercontent.com/nrjalela/opsmesh/main/data/invoices/OPS-0014.pdf"
    assert find_pdf_url(f"see {raw}.") == raw


@pytest.mark.parametrize("url", [
    "https://evil.example/user-attachments/files/1/x.pdf",
    "https://github.com.evil.example/user-attachments/files/1/x.pdf",
    "http://github.com/user-attachments/files/1/x.pdf",
    "https://raw.githubusercontent.com/someone-else/repo/main/x.pdf",
    "https://raw.githubusercontent.com/nrjalela/opsmesh/main/data/invoices/../../.env",
])
def test_rejects_links_from_anywhere_else(url):
    assert find_pdf_url(url) is None


def test_redirects_must_stay_on_github():
    assert is_allowed_redirect("https://objects.githubusercontent.com/abc")
    assert not is_allowed_redirect("https://attacker.example/abc")
    assert not is_allowed_redirect("http://objects.githubusercontent.com/abc")


def test_download_refuses_disallowed_url():
    with pytest.raises(PDFError):
        issue_mod.download_pdf("https://attacker.example/x.pdf")


def test_non_pdf_is_refused():
    with pytest.raises(PDFError):
        check_pdf(b"<html>not a pdf</html>")


@pytest.mark.parametrize("text,action,note", [
    ("/approve Buyer confirmed", "approve", "Buyer confirmed"),
    ("/APPROVE", "approve", ""),
    ("  /reject   wrong GST\nplease resend", "reject", "wrong GST please resend"),
    ("/retry", "retry", ""),
])
def test_parses_commands(text, action, note):
    cmd = parse_command(text)
    assert cmd.action == action and cmd.note == note


@pytest.mark.parametrize("text", ["approve it", "/approved", "please /approve", "", None])
def test_ignores_non_commands(text):
    assert parse_command(text) is None


# --- the pipeline -----------------------------------------------------------------------------

def test_clean_invoice_posts_and_closes(tmp_path, llm):
    store = StateStore(tmp_path)
    out = submit(store, 11, BY_SCENARIO["C01"])
    assert out.status == "posted" and out.add_labels == ["posted"] and out.close
    assert "Posted, no human touch" in out.comment and "What the intake agent read" in out.comment
    assert len(store.ledger()) == 1
    assert [e["event"] for e in store.events()] == ["processed"]


def test_strangers_are_ignored(tmp_path, llm):
    out = process_issue(issue=1, author="someone-else", body=body_for("OPS-0001"), created_at="2026-10-01",
                        store=StateStore(tmp_path), now=NOW, fetch=fetch)
    assert out.status == "ignored" and out.comment is None and llm["intake"] == 0


def test_same_pdf_twice_is_a_duplicate_and_costs_nothing(tmp_path, llm):
    store = StateStore(tmp_path)
    doc = BY_SCENARIO["C02"]
    submit(store, 20, doc)
    out = submit(store, 21, doc)
    assert out.status == "duplicate" and out.close and "#20" in out.comment
    assert llm["intake"] == 1  # the second one never reached the model


def test_posted_live_invoice_feeds_the_engines_duplicate_check(tmp_path, llm):
    store = StateStore(tmp_path)
    doc = BY_SCENARIO["C01"]
    submit(store, 30, doc)
    inv = InvoiceDocument.model_validate(KEY[doc]["invoice"])
    types = [t.value for t in match_invoice(inv, store.master(), load_tolerances()).exception_types]
    assert types == ["duplicate_invoice"]  # e.g. the same invoice re-scanned into a different PDF


def test_held_run_survives_a_restart_and_resumes_on_approve(tmp_path, llm):
    doc = BY_SCENARIO["X01"]  # price variance + short-shipped
    held = submit(StateStore(tmp_path), 40, doc)
    assert held.status == "held" and held.add_labels == ["held"] and not held.close
    assert "/approve" in held.comment and "Three-way match: 2 problems" in held.comment

    # A later Actions run: brand-new objects, same files on the state branch.
    store = StateStore(tmp_path)
    out = comment(store, 40, "/approve Buyer agreed the new bearing price", doc)
    assert out.status == "posted" and out.add_labels == ["posted"] and out.close
    assert "Approved by @nrjalela" in out.comment and "Buyer agreed" in out.comment
    decided = [e for e in store.events() if e["event"] == "decided"][0]
    assert decided["decision"] == "approve" and decided["actor"] == "nrjalela"
    assert decided["same_person_as_submitter"] is True

    again = comment(store, 40, "/approve twice?", doc)
    assert again.status == "noop" and "only count once" in again.comment


def test_reject(tmp_path, llm):
    store = StateStore(tmp_path)
    doc = BY_SCENARIO["D01"]
    submit(store, 50, doc)
    out = comment(store, 50, "/reject Already paid in August", doc)
    assert out.status == "rejected" and out.add_labels == ["rejected"] and out.close
    assert store.ledger() == []


def test_only_the_owner_can_decide(tmp_path, llm):
    store = StateStore(tmp_path)
    doc = BY_SCENARIO["P01"]
    submit(store, 60, doc)
    assert comment(store, 60, "/approve", doc, author="drive-by").status == "ignored"
    assert comment(store, 60, "/approve ok", doc).status == "posted"


def test_daily_cap_defers_then_retry_next_day(tmp_path, llm):
    store = StateStore(tmp_path)
    clean = [d for d, v in KEY.items() if v["category"] == "clean"][:6]
    for i, doc in enumerate(clean[:5]):
        assert submit(store, 100 + i, doc).status == "posted"
    capped = submit(store, 105, clean[5])
    assert capped.status == "over-cap" and capped.add_labels == ["over-cap"] and llm["intake"] == 5
    tomorrow = NOW + timedelta(days=1)
    retried = comment(store, 105, "/retry", clean[5], now=tomorrow)
    assert retried.status == "posted" and "over-cap" in retried.remove_labels


def test_cap_counts_the_australian_day(tmp_path, llm):
    store = StateStore(tmp_path)
    clean = [d for d, v in KEY.items() if v["category"] == "clean"][:6]
    late = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)  # 23:30 Sydney, 1 Oct
    for i, doc in enumerate(clean[:5]):
        submit(store, 200 + i, doc, now=late)
    after_midnight = datetime(2026, 10, 1, 14, 30, tzinfo=timezone.utc)  # 00:30 Sydney, 2 Oct
    assert submit(store, 205, clean[5], now=after_midnight).status == "posted"


def test_missing_attachment_asks_for_retry(tmp_path, llm):
    out = process_issue(issue=70, author="nrjalela", body="no file here", created_at="2026-10-01",
                        store=StateStore(tmp_path), now=NOW, fetch=fetch)
    assert out.status == "error" and "/retry" in out.comment and llm["intake"] == 0


def test_comment_tables_escape_pipes(tmp_path, llm, monkeypatch):
    from opsmesh.live.render import cell
    assert cell("a|b\nc") == "a\\|b c"
