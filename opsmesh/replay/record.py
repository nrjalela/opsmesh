"""Run the batch through the live agents once and save replay files.

    python -m opsmesh.replay.record              # all invoices without a replay yet
    python -m opsmesh.replay.record --only OPS-0001 --force
    python -m opsmesh.replay.record --summary-only

Spends API credits (roughly two Claude calls per exception invoice, one per clean one).
Invoices that already have a replay are skipped unless --force, so an interrupted
run can be picked up without paying twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from opsmesh.agents.graph import build_graph, start_run
from opsmesh.agents.llm import api_key_available, model_name
from opsmesh.config import DATA_DIR, INVOICE_DIR, REPLAY_DIR
from opsmesh.replay.accuracy import score_invoice, summarise
from opsmesh.replay.store import SUMMARY_FILE, build_replay, load_replays, save_replay


def record_one(item: dict) -> dict:
    graph = build_graph()  # own checkpointer per worker
    state = start_run(graph, item["doc_id"], INVOICE_DIR / item["file"], item["received_date"])
    replay = build_replay(state, file=item["file"], model=model_name())
    save_replay(replay)
    return replay


def write_summary() -> dict:
    replays = load_replays()
    key = json.loads((DATA_DIR / "answer_key.json").read_text())
    scores = {d: score_invoice(r["state"]["extraction"], key[d]["invoice"]) for d, r in replays.items()}
    acc = summarise(scores)

    agree = 0
    for d, r in replays.items():
        got = sorted({e["type"] for e in ((r["state"]["match"] or {}).get("exceptions") or [])})
        agree += got == sorted(key[d]["expected_exceptions"])

    statuses = Counter(r["status"] for r in replays.values())
    summary = {
        "invoices": len(replays),
        "model": next(iter(replays.values()))["model"] if replays else None,
        "statuses": dict(statuses),
        "touchless": sum(1 for r in replays.values() if r["state"]["route"] and r["state"]["route"]["action"] == "auto_post"),
        "exceptions_match_answer_key": agree,
        "extraction": {k: v for k, v in acc.items() if k != "errors"},
        "extraction_errors": acc["errors"],
        "cost_usd": round(sum(r["metrics"]["cost_usd"] for r in replays.values()), 4),
        "input_tokens": sum(r["metrics"]["input_tokens"] for r in replays.values()),
        "output_tokens": sum(r["metrics"]["output_tokens"] for r in replays.values()),
    }
    (REPLAY_DIR / SUMMARY_FILE).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated doc ids")
    ap.add_argument("--force", action="store_true", help="re-record even if a replay exists")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    if not args.summary_only:
        if not api_key_available():
            sys.exit("ANTHROPIC_API_KEY is not set (put it in .env). Replay mode needs no key; recording does.")
        index = json.loads((INVOICE_DIR / "index.json").read_text())
        if args.only:
            wanted = set(args.only.split(","))
            index = [i for i in index if i["doc_id"] in wanted]
        existing = set(load_replays())
        todo = [i for i in index if args.force or i["doc_id"] not in existing]
        print(f"Recording {len(todo)} invoice(s) with {model_name()} ({len(index) - len(todo)} already recorded).")
        failures = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(record_one, item): item["doc_id"] for item in todo}
            for fut in as_completed(futures):
                doc = futures[fut]
                try:
                    r = fut.result()
                    m = r["metrics"]
                    print(f"  {doc}  {r['status']:<18} {m['automated_ms'] / 1000:5.1f}s  ${m['cost_usd']:.4f}")
                except Exception as e:  # keep going; the rest of the batch is still worth recording
                    failures.append(doc)
                    print(f"  {doc}  FAILED: {type(e).__name__}: {e}")
        if failures:
            print(f"{len(failures)} failed: {', '.join(sorted(failures))}. Re-run to retry just those.")

    s = write_summary()
    ex = s["extraction"]
    print(f"\n{s['invoices']} replays. Touchless: {s['touchless']}. Statuses: {s['statuses']}")
    print(f"Exceptions agree with answer key: {s['exceptions_match_answer_key']}/{s['invoices']}")
    print(f"Extraction: {ex['fields_correct']}/{ex['fields_total']} fields correct ({ex['field_accuracy']:.1%}); "
          f"{ex['invoices_all_correct']}/{ex['invoices_total']} invoices perfect.")
    print(f"Cost: ${s['cost_usd']:.2f} ({s['input_tokens']:,} in / {s['output_tokens']:,} out tokens)")


if __name__ == "__main__":
    main()
