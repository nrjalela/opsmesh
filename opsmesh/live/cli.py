"""Entry point for the OpsMesh Live workflow.

    python -m opsmesh.live.cli issue    --state state --out out   # a new invoice issue
    python -m opsmesh.live.cli comment  --state state --out out   # /approve, /reject, /retry

Inputs come from environment variables set by the workflow (never interpolated into
shell). Writes out/result.json and out/comment.md for the workflow to apply.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from opsmesh.live.issue import download_pdf
from opsmesh.live.runner import handle_comment, process_issue
from opsmesh.live.state import StateStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("event", choices=["issue", "comment"])
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    env = os.environ
    store = StateStore(args.state)
    token = env.get("GITHUB_TOKEN")
    fetch = lambda url: download_pdf(url, token=token)  # noqa: E731
    common = dict(issue=int(env["ISSUE_NUMBER"]), store=store, fetch=fetch, created_at=env["ISSUE_CREATED_AT"],
                  run_url=env.get("RUN_URL"), cap=int(env.get("DAILY_CAP", "5")), owner=env.get("OWNER", "nrjalela"))
    if args.event == "issue":
        outcome = process_issue(author=env["ISSUE_AUTHOR"], body=env.get("ISSUE_BODY", ""), **common)
    else:
        outcome = handle_comment(author=env["COMMENT_AUTHOR"], comment_body=env.get("COMMENT_BODY", ""),
                                 issue_body=env.get("ISSUE_BODY", ""), **common)

    args.out.mkdir(parents=True, exist_ok=True)
    if outcome.comment:
        (args.out / "comment.md").write_text(outcome.comment)
    (args.out / "result.json").write_text(json.dumps({
        "status": outcome.status, "comment": bool(outcome.comment), "add_labels": outcome.add_labels,
        "remove_labels": outcome.remove_labels, "close": outcome.close,
    }))
    print(f"issue #{common['issue']}: {outcome.status}")


if __name__ == "__main__":
    main()
