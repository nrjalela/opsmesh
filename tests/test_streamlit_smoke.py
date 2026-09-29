"""The local Streamlit console runs in replay mode with no API key."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from opsmesh.config import ROOT

ENTRY = str(ROOT / "streamlit_app.py")

PAGES = ["app/views/queue.py", "app/views/invoice.py", "app/views/inbox.py", "app/views/dashboard.py"]


@pytest.fixture
def no_key(monkeypatch):
    # Empty (not unset) so load_dotenv can't pull a real key in from .env.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("LIVE_MODE_PASSWORD", "")


def test_every_page_renders_without_an_api_key(no_key):
    at = AppTest.from_file(ENTRY, default_timeout=60).run()
    assert not at.exception
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, page
    assert "isn't configured" in " ".join(c.value for c in at.sidebar.caption)


def test_replay_approval_in_the_console(no_key):
    at = AppTest.from_file(ENTRY, default_timeout=60).run()
    at.switch_page("app/views/invoice.py").run()
    at.selectbox[0].set_value("OPS-0034").run()  # clean but $133k: waits for the Finance Manager
    at.text_input[0].input("Signed off by the plant manager")
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception
    assert at.session_state["decided"]["OPS-0034"]["status"] == "posted"


def test_live_password_check(monkeypatch):
    from app.ui import check_password

    monkeypatch.setenv("LIVE_MODE_PASSWORD", "correct horse")
    assert check_password("correct horse")
    assert not check_password("wrong")
    monkeypatch.setenv("LIVE_MODE_PASSWORD", "")
    assert not check_password("")  # an unset password never unlocks
