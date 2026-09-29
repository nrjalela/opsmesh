from collections import defaultdict
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from app.ui import all_runs, batch_summary, esc, exception_types, money, secs, total_of, touchless

ACCENT, INK, MUTED, GRID = "#B4532A", "#2B2A28", "#6B645C", "#E6DED2"

st.title("AP dashboard")
st.markdown(
    '<div class="om-muted">The September batch at a glance. Figures update as you approve or reject invoices '
    "in the inbox.</div>", unsafe_allow_html=True)

runs = all_runs()
n = len(runs)
touch = [r for r in runs.values() if touchless(r)]
held = [r for r in runs.values() if r["status"] == "awaiting_approval" and exception_types(r)]
signoff = [r for r in runs.values() if r["status"] == "awaiting_approval" and not exception_types(r)]
on_hold = sum((total_of(r) or Decimal(0) for r in held), Decimal(0))
awaiting_signoff = sum((total_of(r) or Decimal(0) for r in signoff), Decimal(0))
avg_touchless_ms = sum(r["metrics"]["automated_ms"] for r in touch) / len(touch) if touch else 0
summary = batch_summary() or {}
ex = summary.get("extraction") or {}

st.write("")
k1, k2, k3, k4 = st.columns(4)
with k1.container(border=True):
    st.metric("Touchless rate", f"{len(touch) / n:.0%}" if n else "-",
              help="Invoices posted with no human touch: read, matched, routed and posted by the agents.")
    st.caption(f"{len(touch)} of {n} invoices posted with no human touch")
with k2.container(border=True):
    st.metric("Avg cycle time, touchless", secs(int(avg_touchless_ms)),
              help="PDF received to posted in the ledger, measured on the recorded runs. Held invoices wait "
                   "for a person, so their clock is still running.")
    st.caption("PDF in to posted, measured")
with k3.container(border=True):
    st.metric("Value on hold", money(on_hold), help="Invoices blocked for an exception, inc GST.")
    st.caption(esc(f"{len(held)} invoices with exceptions · {money(awaiting_signoff)} more awaiting sign-off"))
with k4.container(border=True):
    st.metric("Extraction accuracy", f"{ex['field_accuracy']:.1%}" if ex else "-",
              help="Fields the intake agent read from the PDF that exactly match the answer key.")
    st.caption(f"{ex.get('fields_correct', 0)} of {ex.get('fields_total', 0)} fields, {ex.get('invoices_total', 0)} invoices")

# --- exceptions by type ---------------------------------------------------------------------
counts: dict[str, int] = defaultdict(int)
value: dict[str, Decimal] = defaultdict(Decimal)
for r in runs.values():
    for t in exception_types(r):
        counts[t.label] += 1
        value[t.label] += total_of(r) or Decimal(0)
df = pd.DataFrame([{"Exception": k, "Invoices": v, "Value": float(value[k])} for k, v in counts.items()])

st.write("")
chart_col, stats_col = st.columns([2, 1], gap="large")
with chart_col:
    st.markdown("#### Exceptions caught, by type")
    st.markdown('<div class="om-muted">Invoices stopped by the three-way match. One invoice can have more than one.</div>',
                unsafe_allow_html=True)
    if df.empty:
        st.caption("No exceptions.")
    else:
        base = alt.Chart(df).encode(
            y=alt.Y("Exception:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=280, labelFontSize=13, labelColor=INK, ticks=False, domain=False, labelPadding=10)),
            x=alt.X("Invoices:Q", title=None,
                    axis=alt.Axis(tickMinStep=1, format="d", grid=True, gridColor=GRID, gridWidth=1, domain=False,
                                  ticks=False, labelColor=MUTED, labelFontSize=12)),
            tooltip=[alt.Tooltip("Exception:N"), alt.Tooltip("Invoices:Q"),
                     alt.Tooltip("Value:Q", format="$,.2f", title="Invoice value")],
        )
        bars = base.mark_bar(color=ACCENT, size=20, cornerRadiusEnd=4)
        tips = base.mark_text(align="left", dx=6, color=INK, fontSize=13, fontWeight=600).encode(text="Invoices:Q")
        chart = ((bars + tips).properties(height=44 * len(df) + 20)
                 .configure(font="Figtree", background="transparent")
                 .configure_view(strokeWidth=0))
        st.altair_chart(chart, width="stretch", theme=None)
        with st.expander("Show as a table"):
            st.dataframe(df.sort_values("Invoices", ascending=False), hide_index=True, width="stretch",
                         column_config={"Value": st.column_config.NumberColumn("Invoice value", format="dollar")})

with stats_col:
    st.markdown("#### The recorded run")
    held_all = [r for r in runs.values() if not touchless(r)]
    avg_held = sum(r["metrics"]["automated_ms"] for r in held_all) / len(held_all) if held_all else 0
    cost = summary.get("cost_usd", 0)
    lines = [
        ("Model", summary.get("model", "-")),
        ("API cost, whole batch", f"${cost:.2f} (${cost / max(summary.get('invoices', 1), 1):.3f} per invoice)"),
        ("Exceptions matching the answer key", f"{summary.get('exceptions_match_answer_key', '-')} of {summary.get('invoices', '-')}"),
        ("Invoices read perfectly", f"{ex.get('invoices_all_correct', '-')} of {ex.get('invoices_total', '-')}"),
        ("Avg automated time, held invoices", secs(int(avg_held))),
    ]
    for label, v in lines:
        st.markdown(f"<div class='om-muted'>{label}</div><div style='margin-bottom:.7rem'><strong>{esc(v)}</strong></div>",
                    unsafe_allow_html=True)
