import streamlit as st

from app.ui import ROLES, all_runs, decision_form, esc, issue_text, money, recorded_runs, total_of, undo, vendor_of

st.title("Approval inbox")
st.markdown(
    '<div class="om-muted">Invoices the approval router paused for a person. In replay mode your decisions last '
    "for this browser session only, so go ahead and try them.</div>",
    unsafe_allow_html=True,
)


@st.dialog("Review invoice", width="large")
def review(doc_id: str) -> None:
    # A modal bound to one invoice: it closes on decision, so the next click can't land on a different invoice.
    run = all_runs()[doc_id]
    inv = run["state"].get("invoice") or {}
    st.markdown(f"**{vendor_of(run)}** &nbsp; {esc(money(total_of(run)))} &nbsp;"
                f"<span class='om-muted'>{doc_id} · invoice {inv.get('invoice_number', '?')}</span>",
                unsafe_allow_html=True)
    for reason in run["pending"]["reasons"]:
        st.markdown(f"- {esc(reason)}")
    analysis = run["state"].get("analysis")
    if analysis:
        st.markdown(esc(analysis["explanation"]))
    decision_form(run, key="inbox")


runs = all_runs()
waiting = {d: r for d, r in runs.items() if r["status"] == "awaiting_approval"}

if not waiting:
    st.success("Inbox zero. Every invoice has been decided.", icon=":material/done_all:")

for role in ROLES:
    mine = {d: r for d, r in waiting.items() if r["pending"]["approver"] == role}
    if not mine:
        continue
    st.write("")
    st.markdown(f"#### {role} &nbsp;<span class='om-muted'>{len(mine)} waiting</span>", unsafe_allow_html=True)
    for doc_id, run in mine.items():
        with st.container(border=True):
            info, act = st.columns([4, 1.3], vertical_alignment="center")
            with info:
                inv = run["state"].get("invoice") or {}
                st.markdown(f"**{vendor_of(run)}** &nbsp; {esc(money(total_of(run)))} &nbsp;"
                            f"<span class='om-muted'>{doc_id} · invoice {inv.get('invoice_number', '?')}</span>",
                            unsafe_allow_html=True)
                analysis = run["state"].get("analysis")
                st.markdown(esc(analysis["headline"] if analysis else " ".join(run["pending"]["reasons"])))
                st.caption(issue_text(run))
            with act:
                if st.button("Review", key=f"review-{doc_id}", width="stretch"):
                    review(doc_id)
                if st.button("Open invoice", key=f"open-{doc_id}", type="tertiary", width="stretch"):
                    st.session_state.selected_doc = doc_id
                    st.switch_page("app/views/invoice.py")

decided = {d: r for d, r in st.session_state.get("decided", {}).items()}
if decided:
    st.write("")
    st.markdown("#### Decided this session")
    for doc_id, run in decided.items():
        outcome = run["state"]["outcome"]
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        verb = "Posted" if outcome["status"] == "posted" else "Rejected"
        note = esc(f' "{outcome["note"]}"') if outcome.get("note") else ""
        c1.markdown(f"{verb} **{vendor_of(run)}** {esc(money(total_of(run)))} <span class='om-muted'>{doc_id}{note}</span>",
                    unsafe_allow_html=True)
        if doc_id in recorded_runs() and c2.button("Undo", key=f"undo-{doc_id}", type="tertiary"):
            undo(doc_id)
            st.rerun()
