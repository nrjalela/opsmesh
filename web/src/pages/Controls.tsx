import { useApp } from "../app-context";
import { REPO_URL } from "../components/Layout";
import { money } from "../format";

const NEW_ISSUE = `${REPO_URL}/issues/new?template=submit-invoice.yml`;

interface Control {
  title: string;
  points: React.ReactNode[];
}

export function ControlsPage() {
  const { batch } = useApp();
  const limit = money(batch.auto_post_limit);

  const controls: Control[] = [
    {
      title: "Approval limits",
      points: [
        <>A clean, PO-matched invoice up to {limit} (inc GST) posts with no human touch. The PO was already approved when it was raised.</>,
        <>Clean invoices above {limit} go to the AP Supervisor, and above $100,000.00 to the Finance Manager.</>,
        <>Any invoice with an exception goes to an AP Officer; an unknown vendor goes to the AP Supervisor.</>,
        <>If the intake agent is less than 80% sure of any key field, a person checks it before anything posts.</>,
        <>The limits live in a config file, <code>config/approval_rules.yaml</code>, not in a prompt.</>,
      ],
    },
    {
      title: "Matching rules",
      points: [
        <>Plain, tested code does the three-way match: purchase order, goods receipt and invoice. The AI never decides whether an invoice gets paid.</>,
        <>A price above PO is blocked if it's more than 2% or more than $250 on a line, whichever is lower.</>,
        <>Quantities are checked against goods received, net of what's already been invoiced. Services are matched against the PO (two-way).</>,
        <>GST is recalculated from the PO's tax codes, with a 5¢ rounding allowance.</>,
      ],
    },
    {
      title: "Fraud and error checks",
      points: [
        <>Every ABN is checked against the ATO checksum and the vendor master.</>,
        <>A vendor name that matches a known supplier but with a different ABN is treated as possible impersonation, especially when the invoice asks for new bank details.</>,
        <>Duplicates are caught by invoice number (even with prefixes or leading zeros changed), and by same amount within 7 days.</>,
        <>In live mode, the exact same PDF is also caught by its SHA-256 hash, before any AI call, so it costs nothing.</>,
        <>Code, not the AI, decides who each drafted message goes to, so a suspected fraudster's email address can never be put in the To: line. Nothing is sent automatically.</>,
      ],
    },
    {
      title: "Segregation of duties and who can act",
      points: [
        <>In this replay site, anyone can approve or reject, but decisions stay in their own browser and change nothing for anyone else.</>,
        <>
          In live mode, only <strong>@nrjalela</strong> can submit an invoice or run <code>/approve</code>,{" "}
          <code>/reject</code> or <code>/retry</code>. Issues and comments from anyone else never start a job
          that can see the API key.
        </>,
        <>
          <strong>Honest limitation:</strong> this is a one-person demo, so the same account both submits and
          approves. Segregation of duties can't be enforced with one person. The audit log flags every such
          decision, and a real deployment would use separate submitter and approver lists.
        </>,
        <>A decision only counts once. A second <code>/approve</code> on the same invoice is refused.</>,
      ],
    },
    {
      title: "Audit trail",
      points: [
        <>Every invoice has a step log: what each agent or rule did, why, how long it took and what it cost. You can read all of it on each invoice page.</>,
        <>
          In live mode, every event (processed, duplicate, deferred, decided: who, what, when and the note) is
          appended to <code>audit.jsonl</code> on the <code>opsmesh-state</code> branch. Each change is a git
          commit, so the history can't be quietly rewritten without it showing.
        </>,
      ],
    },
    {
      title: "Identity, access and secrets",
      points: [
        <>The Claude API key is stored as an encrypted GitHub Actions secret, never in the code or the repo history.</>,
        <>The workflow's token can only write issues and the state branch, and nothing else.</>,
        <>Issue and comment text is treated as untrusted. It reaches the code as data, never pasted into shell commands. PDFs are only fetched from GitHub's own attachment host or this repo's sample invoices.</>,
      ],
    },
    {
      title: "Spend controls",
      points: [
        <>Live mode processes at most <strong>5 invoices a day</strong> (Australian time). Extras wait for a <code>/retry</code> the next day.</>,
        <>The recorded batch cost ${batch.summary.cost_usd.toFixed(2)} in API calls for {batch.summary.invoices} invoices, about ${(batch.summary.cost_usd / batch.summary.invoices).toFixed(3)} each.</>,
      ],
    },
    {
      title: "Where data is stored and processed",
      points: [
        <><strong>All data here is synthetic.</strong> Live mode is for the sample invoices only.</>,
        <>This site is static files on GitHub Pages; approvals you make here stay in your browser.</>,
        <>
          In live mode, the PDF and the bot's comments are stored in <strong>public</strong> GitHub issues. The
          pipeline runs on GitHub-hosted runners, and invoice content is sent to Anthropic's Claude API for
          reading and explaining. Neither guarantees processing in Australia, so this is not an
          Australian-data-residency setup.
        </>,
        <>An Azure version with more control over where data lives is planned; see <a href={`${REPO_URL}/blob/main/docs/azure-plan.md`}>docs/azure-plan.md</a>.</>,
      ],
    },
  ];

  return (
    <>
      <section className="intro">
        <p className="kicker">Controls, in plain English</p>
        <h1>How OpsMesh keeps AP safe</h1>
        <p className="lede">
          The checks an auditor or finance lead would ask about: who can approve what, what's checked before
          anything is paid, what's logged, and where the data goes. It covers this replay site and the live
          mode, where an invoice submitted as a GitHub issue runs through the real pipeline.{" "}
          <a href={NEW_ISSUE}>Submit an invoice</a> (repo owner only).
        </p>
      </section>
      <div className="controls">
        {controls.map((c) => (
          <section key={c.title} className="panel control">
            <h2>{c.title}</h2>
            <ul>
              {c.points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
