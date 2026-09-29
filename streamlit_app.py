"""OpsMesh: multi-agent procure-to-pay automation demo.

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from opsmesh.config import ROOT

load_dotenv(ROOT / ".env")

from app.ui import all_runs, check_password, footer, inject_css, live_configured, live_unlocked  # noqa: E402

st.set_page_config(page_title="OpsMesh: AP automation demo", page_icon=":material/receipt_long:", layout="wide")
inject_css()

pending = sum(1 for r in all_runs().values() if r["status"] == "awaiting_approval")
pages = [
    st.Page("app/views/queue.py", title="Invoice queue", icon=":material/list_alt:", default=True),
    st.Page("app/views/invoice.py", title="Invoice detail", icon=":material/description:"),
    st.Page("app/views/inbox.py", title=f"Approval inbox ({pending})", icon=":material/inbox:"),
    st.Page("app/views/dashboard.py", title="AP dashboard", icon=":material/insights:"),
]
if live_unlocked():
    pages.append(st.Page("app/views/live.py", title="Run live", icon=":material/play_circle:"))
nav = st.navigation(pages)

with st.sidebar:
    st.markdown("### OpsMesh")
    st.markdown(
        '<div class="om-muted">Accounts payable automation for Corio Packaging, '
        "a fictional packaging manufacturer in Geelong.</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    if live_unlocked():
        st.markdown("**Mode: Live**")
        st.caption("Runs the real agents. Each run uses API credits.")
        if st.button("Back to replay mode", width="stretch"):
            st.session_state.live_unlocked = False
            st.rerun()
    else:
        st.markdown("**Mode: Replay**")
        st.caption("You're watching recorded agent runs. Free, and no API key needed.")
        with st.expander("Switch to live mode"):
            if not live_configured():
                st.caption("Live mode isn't configured. Add ANTHROPIC_API_KEY and LIVE_MODE_PASSWORD to .env, then restart.")
            else:
                with st.form("unlock", border=False):
                    pw = st.text_input("Password", type="password")
                    if st.form_submit_button("Unlock live mode", width="stretch"):
                        if check_password(pw):
                            st.session_state.live_unlocked = True
                            st.rerun()
                        else:
                            st.error("That password didn't work.")
    st.divider()
    st.caption("Synthetic data only. Every vendor, invoice and ABN here is made up.")

nav.run()
footer()
