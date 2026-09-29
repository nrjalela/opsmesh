// Smoke test: the replay site runs end to end from the committed batch.json. No API key, no network.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import rawBatch from "../../public/data/batch.json";
import { App } from "../App";
import { applyDecision, loadDecisions, withDecisions } from "../model";
import type { Batch } from "../types";

const batch = rawBatch as unknown as Batch;

function goTo(hash: string) {
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
}

beforeEach(() => {
  window.localStorage.clear();
  window.scrollTo = () => {};
  window.location.hash = "#/";
});
afterEach(cleanup);

describe("replay site", () => {
  it("lists every recorded invoice in the queue", () => {
    render(<App batch={batch} />);
    expect(screen.getByRole("heading", { name: "Invoice queue" })).toBeTruthy();
    const rows = screen.getAllByRole("row").slice(1); // minus the header row
    expect(rows).toHaveLength(batch.runs.length);
    expect(batch.runs.length).toBe(40);
  });

  it("approves an invoice from the inbox and posts it", () => {
    render(<App batch={batch} />);
    goTo("#/inbox");
    const waitingBefore = batch.runs.filter((r) => r.status === "awaiting_approval").length;
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByText(String(waitingBefore))).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Review" })[0]);
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Note for the audit trail"), {
      target: { value: "Checked with the buyer" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve and post" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(nav).getByText(String(waitingBefore - 1))).toBeTruthy();
    const saved = loadDecisions();
    const [docId] = Object.keys(saved);
    expect(saved[docId]).toMatchObject({ decision: "approve", note: "Checked with the buyer" });

    goTo(`#/invoice/${docId}`);
    expect(screen.getAllByText(/Posted as document/).length).toBe(2); // banner + timeline step
    expect(screen.getByText("Human approval")).toBeTruthy();
  });

  it("renders every invoice page and the dashboard", () => {
    render(<App batch={batch} />);
    for (const run of batch.runs) {
      goTo(`#/invoice/${run.doc_id}`);
      expect(screen.getByText("How it was processed")).toBeTruthy();
    }
    goTo("#/dashboard");
    expect(screen.getByText("Touchless rate")).toBeTruthy();
    expect(screen.getByText(`${Math.round((batch.summary.touchless / batch.summary.invoices) * 100)}%`)).toBeTruthy();
  });
});

describe("amber is reserved for holds and exceptions", () => {
  it("a clean, auto-posted invoice shows no warning styling", () => {
    const { container } = render(<App batch={batch} />);
    goTo("#/invoice/OPS-0001");
    expect(container.querySelectorAll(".conf-low, .callout-warn, .pill-wait, .panel-accent")).toHaveLength(0);
  });

  it("low-confidence markers match what the router flagged", () => {
    const { container } = render(<App batch={batch} />);
    for (const run of batch.runs) {
      goTo(`#/invoice/${run.doc_id}`);
      const flagged = run.state.route!.reasons.some((r) => r.includes("Low-confidence"));
      expect(container.querySelectorAll(".conf-low").length > 0, run.doc_id).toBe(flagged);
    }
  });

  it("only the bank-details remark is flagged", () => {
    const { container } = render(<App batch={batch} />);
    const flaggedDocs = batch.runs.filter((run) => {
      goTo(`#/invoice/${run.doc_id}`);
      return container.querySelector(".callout-warn") !== null;
    });
    expect(flaggedDocs.map((r) => r.doc_id)).toEqual(["OPS-0022"]);
  });
});

describe("decisions", () => {
  it("reject uses the precomputed outcome and keeps the note", () => {
    const paused = batch.runs.find((r) => r.pending)!;
    const done = applyDecision(batch, paused, {
      decision: "reject",
      note: "Duplicate",
      reviewer: paused.pending!.approver,
      decidedAt: "2026-09-30T00:00:00Z",
    });
    expect(done.status).toBe("rejected");
    expect(done.pending).toBeNull();
    expect(done.steps.at(-1)?.node).toBe("reject");
    expect(done.state.outcome).toMatchObject({ status: "rejected", note: "Duplicate" });
  });

  it("ignores decisions for invoices that were never paused", () => {
    const posted = batch.runs.find((r) => r.status === "posted")!;
    const runs = withDecisions(batch, {
      [posted.doc_id]: { decision: "reject", note: "", reviewer: "x", decidedAt: "" },
    });
    expect(runs.find((r) => r.doc_id === posted.doc_id)?.status).toBe("posted");
  });

  it("survives unreadable browser storage", () => {
    window.localStorage.setItem("opsmesh.decisions.v1", "{not json");
    expect(loadDecisions()).toEqual({});
  });
});
