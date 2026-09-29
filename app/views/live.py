import json
from datetime import date

import streamlit as st

from app.live import max_runs, next_live_id, runs_left, save_upload, stream_run
from app.ui import KIND_ICON, all_runs, decision_form, esc, live_unlocked, secs, status_badge
from opsmesh.config import INVOICE_DIR

if not live_unlocked():
    st.warning("Live mode is locked.")
    st.stop()

st.title("Run live")
st.markdown(
    f'<div class="om-muted">Runs the real agents on one invoice. Each run makes one or two Claude calls '
    f"(about \\$0.01 to \\$0.03). {runs_left()} of {max_runs()} runs left this session.</div>",
    unsafe_allow_html=True,
)

index = json.loads((INVOICE_DIR / "index.json").read_text())
source = st.radio("Invoice", ["One of the 40 sample invoices", "Upload a PDF"], horizontal=True,
                  label_visibility="collapsed")
pdf, received = None, date.today().isoformat()
if source.startswith("One"):
    pick = st.selectbox("Sample invoice", [i["doc_id"] for i in index])
    item = next(i for i in index if i["doc_id"] == pick)
    pdf, received = INVOICE_DIR / item["file"], item["received_date"]
else:
    up = st.file_uploader("Invoice PDF (one page works best, 5 MB max)", type=["pdf"])
    if up is not None and up.size > 5 * 1024 * 1024:
        st.error("That file is over 5 MB.")
        up = None
    if up is not None:
        pdf = up

run_it = st.button("Run the agents", type="primary", disabled=pdf is None or runs_left() == 0)
if runs_left() == 0:
    st.caption("You've used this session's live runs.")

if run_it and pdf is not None:
    doc_id = next_live_id()
    path = pdf if not hasattr(pdf, "getvalue") else save_upload(doc_id, pdf.getvalue())
    with st.status(f"Running {doc_id}…", expanded=True) as status:
        try:
            for step in stream_run(doc_id, path, received):
                st.markdown(f"{KIND_ICON[step['kind']]} **{step['title']}** · {secs(step['duration_ms'])}  \n"
                            f"{esc(step['summary'])}")
            status.update(label=f"{doc_id} finished", state="complete")
        except Exception as e:  # show it; don't take the app down
            status.update(label="The run failed", state="error")
            st.error(f"{type(e).__name__}: {e}")
    st.session_state.selected_doc = doc_id

live = {d: r for d, r in all_runs().items() if r.get("live")}
if live:
    st.write("")
    st.markdown("#### Your live runs")
    for doc_id, run in reversed(list(live.items())):
        with st.container(border=True):
            a, b = st.columns([4, 1], vertical_alignment="center")
            a.markdown(f"**{doc_id}** · {run['file']}")
            with a:
                status_badge(run)
            if b.button("Open", key=f"open-{doc_id}", width="stretch"):
                st.session_state.selected_doc = doc_id
                st.switch_page("app/views/invoice.py")
            if run["status"] == "awaiting_approval":
                decision_form(run, key="live")
