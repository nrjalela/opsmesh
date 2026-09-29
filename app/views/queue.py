import pandas as pd
import streamlit as st

from app.ui import all_runs, issue_text, status_text, total_of, vendor_of

st.title("Invoice queue")
st.markdown(
    '<div class="om-muted">Supplier invoices received by Corio Packaging\'s accounts payable team in September 2026. '
    "Each one was read by the intake agent, checked against the purchase order and goods receipt, and routed. "
    "Pick a row to see how it was handled.</div>",
    unsafe_allow_html=True,
)

runs = all_runs()
posted = sum(r["status"] == "posted" for r in runs.values())
waiting = sum(r["status"] == "awaiting_approval" for r in runs.values())
rejected = sum(r["status"] == "rejected" for r in runs.values())
st.write("")
st.markdown(f"**{len(runs)}** invoices &nbsp;·&nbsp; **{posted}** posted &nbsp;·&nbsp; "
            f"**{waiting}** waiting for approval &nbsp;·&nbsp; **{rejected}** rejected")

show = st.segmented_control("Show", ["All", "Waiting for approval", "Posted", "Rejected"], default="All",
                            label_visibility="collapsed")
wanted = {"All": None, "Waiting for approval": "awaiting_approval", "Posted": "posted", "Rejected": "rejected"}[show or "All"]

rows = []
for doc_id, r in runs.items():
    if wanted and r["status"] != wanted:
        continue
    inv = r["state"].get("invoice") or {}
    total = total_of(r)
    rows.append({
        "Doc": doc_id,
        "Received": r.get("received_date") or "",
        "Vendor": vendor_of(r),
        "Invoice no.": inv.get("invoice_number") or "",
        "Total (inc GST)": float(total) if total is not None else None,
        "Status": status_text(r),
        "Issue": issue_text(r),
    })
df = pd.DataFrame(rows)

if df.empty:
    st.info("Nothing here yet.")
else:
    event = st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        height=min(38 * len(df) + 40, 760),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Doc": st.column_config.TextColumn(width="small"),
            "Received": st.column_config.DateColumn(format="D MMM", width="small"),
            "Total (inc GST)": st.column_config.NumberColumn(format="dollar"),
            "Vendor": st.column_config.TextColumn(width="medium"),
            "Status": st.column_config.TextColumn(width="medium"),
            "Issue": st.column_config.TextColumn(width="large", help="What stopped the invoice from posting on its own"),
        },
        key="queue_table",
    )
    if event.selection.rows:
        st.session_state.selected_doc = df.iloc[event.selection.rows[0]]["Doc"]
        st.switch_page("app/views/invoice.py")
