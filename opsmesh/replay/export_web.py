"""Bundle the recorded runs for the static React site.

    python -m opsmesh.replay.export_web

Writes web/public/data/batch.json and one image + PDF per invoice. Anything the
browser would otherwise have to compute with business rules (posting document
number, due date from vendor terms) is computed here, by the same Python code
the live graph uses, so the web app never re-implements AP logic.
"""

from __future__ import annotations

import json
import shutil

import pypdfium2 as pdfium

from opsmesh.agents.graph import finalise
from opsmesh.agents.router import load_rules
from opsmesh.config import INVOICE_DIR, ROOT
from opsmesh.engine.matching import ExceptionType
from opsmesh.replay.store import load_replays, load_summary

WEB_PUBLIC = ROOT / "web" / "public"
DATA_OUT = WEB_PUBLIC / "data"
INVOICES_OUT = WEB_PUBLIC / "invoices"


def _preview(replay: dict, action: str) -> dict:
    """What approving or rejecting this paused invoice would record."""
    state = {**replay["state"], "doc_id": replay["doc_id"],
             "decision": {"decision": "approve" if action == "post" else "reject", "note": None, "reviewer": None}}
    result = finalise(state, action)
    step = result["steps"][0] | {"started_at": "", "duration_ms": 0}
    return {"outcome": result["outcome"], "step": step}


def _render(doc_id: str) -> None:
    src = INVOICE_DIR / f"{doc_id}.pdf"
    page = pdfium.PdfDocument(src)[0]
    page.render(scale=1.6).to_pil().convert("RGB").save(INVOICES_OUT / f"{doc_id}.webp", "WEBP", quality=88, method=6)
    shutil.copyfile(src, INVOICES_OUT / f"{doc_id}.pdf")


def main() -> None:
    replays = load_replays()
    summary = load_summary()
    if not replays or summary is None:
        raise SystemExit("No replays found. Run `python -m opsmesh.replay.record` first.")
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    INVOICES_OUT.mkdir(parents=True, exist_ok=True)

    decisions = {}
    for doc_id, r in replays.items():
        _render(doc_id)
        if r["pending"]:
            decisions[doc_id] = {"approve": _preview(r, "post"), "reject": _preview(r, "reject")}

    rules = load_rules()
    bundle = {
        "summary": summary,
        "roles": rules.roles,
        "auto_post_limit": str(rules.auto_post_limit),
        "exception_labels": {t.value: {"label": t.label, "owner": t.owner} for t in ExceptionType},
        "runs": list(replays.values()),
        "decision_previews": decisions,
    }
    (DATA_OUT / "batch.json").write_text(json.dumps(bundle, separators=(",", ":")) + "\n")
    size = (DATA_OUT / "batch.json").stat().st_size
    print(f"Exported {len(replays)} runs ({size / 1024:.0f} KB), {len(decisions)} decision previews, "
          f"{len(replays)} invoice images to {WEB_PUBLIC.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
