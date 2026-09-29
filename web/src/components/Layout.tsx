import type { ReactNode } from "react";
import { useApp } from "../app-context";
import { day } from "../format";
import { href, type RouteMatch } from "../router";

export const REPO_URL = "https://github.com/nrjalela/opsmesh";

function Label({ long, short }: { long: string; short: string }) {
  return (
    <>
      <span className="label-long">{long}</span>
      <span className="label-short">{short}</span>
    </>
  );
}

export function Layout({ route, children }: { route: RouteMatch; children: ReactNode }) {
  const { runs, batch } = useApp();
  const waiting = runs.filter((r) => r.status === "awaiting_approval").length;
  const links: { to: RouteMatch; label: ReactNode; active: boolean }[] = [
    {
      to: { page: "queue" },
      label: <Label long="Invoice queue" short="Queue" />,
      active: route.page === "queue" || route.page === "invoice",
    },
    {
      to: { page: "inbox" },
      label: (
        <>
          <Label long="Approval inbox" short="Inbox" /> {waiting > 0 && <span className="count">{waiting}</span>}
        </>
      ),
      active: route.page === "inbox",
    },
    { to: { page: "dashboard" }, label: <Label long="AP dashboard" short="Dashboard" />, active: route.page === "dashboard" },
  ];
  const recorded = batch.runs[0]?.recorded_at;
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/">
            <span className="brand-mark" aria-hidden="true" />
            OpsMesh
          </a>
          <nav aria-label="Main">
            {links.map((l) => (
              <a key={l.to.page} href={href(l.to)} className={l.active ? "active" : undefined}
                 aria-current={l.active ? "page" : undefined}>
                {l.label}
              </a>
            ))}
          </nav>
          <span className="mode" title="These are recorded runs. Live mode runs locally; see the README.">
            Replay
          </span>
        </div>
      </header>
      <main className="page">{children}</main>
      <footer className="footer">
        <p>
          <strong>Synthetic data.</strong> Corio Packaging, its vendors, people, invoices, ABNs and addresses are all
          made up. ABNs are generated to pass the ATO checksum, so any match with a real business is coincidental.
        </p>
        <p>
          Recorded {recorded ? day(recorded) : ""} with {batch.summary.model} via LangGraph. Built by{" "}
          <a href="https://github.com/nrjalela">nrjalela</a> · <a href={REPO_URL}>Source and README</a>
        </p>
      </footer>
    </div>
  );
}
