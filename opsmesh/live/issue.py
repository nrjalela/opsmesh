"""Reading GitHub issues: where the PDF is, and what a comment is asking for.

Everything here treats issue text as untrusted input. The PDF is only fetched
from GitHub's own attachment host or this repo's sample invoices, and every
redirect is checked against the same rules.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

ALLOWED_PREFIXES = (
    "https://github.com/user-attachments/files/",
    "https://github.com/user-attachments/assets/",
    "https://raw.githubusercontent.com/nrjalela/opsmesh/main/data/invoices/",
    "https://github.com/nrjalela/opsmesh/raw/main/data/invoices/",
)
# GitHub serves attachments by redirecting to its own content hosts.
REDIRECT_HOSTS = ("github.com", "raw.githubusercontent.com")
REDIRECT_HOST_SUFFIXES = (".githubusercontent.com",)
MAX_PDF_BYTES = 10 * 1024 * 1024

_URL = re.compile(r"https://[^\s)\]>\"'<]+")


def is_allowed_url(url: str) -> bool:
    return url.startswith(ALLOWED_PREFIXES) and ".." not in url


def is_allowed_redirect(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and (host in REDIRECT_HOSTS or host.endswith(REDIRECT_HOST_SUFFIXES))


def find_pdf_url(body: str | None) -> str | None:
    """First allowed link in the issue body. Links ending in .pdf win over bare attachment links."""
    candidates = [u.rstrip(".,;") for u in _URL.findall(body or "")]
    allowed = [u for u in candidates if is_allowed_url(u)]
    pdfs = [u for u in allowed if urlparse(u).path.lower().endswith(".pdf")]
    return (pdfs or allowed or [None])[0]


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_redirect(newurl):
            raise ValueError(f"Refusing to follow redirect to {urlparse(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PDFError(ValueError):
    """The attachment couldn't be used; the message is safe to show in a comment."""


def download_pdf(url: str, token: str | None = None) -> bytes:
    if not is_allowed_url(url):
        raise PDFError("That link isn't a GitHub attachment or one of this repo's sample invoices.")
    req = urllib.request.Request(url, headers={"User-Agent": "opsmesh-live"})
    if token and urlparse(url).hostname == "github.com":
        req.add_unredirected_header("Authorization", f"Bearer {token}")  # never forwarded on redirect
    opener = urllib.request.build_opener(_CheckedRedirects)
    try:
        with opener.open(req, timeout=30) as resp:
            data = resp.read(MAX_PDF_BYTES + 1)
    except ValueError as e:
        raise PDFError(str(e)) from e
    except OSError as e:
        raise PDFError(f"Couldn't download the attachment ({type(e).__name__}).") from e
    return check_pdf(data)


def check_pdf(data: bytes) -> bytes:
    if len(data) > MAX_PDF_BYTES:
        raise PDFError("The PDF is over 10 MB.")
    if not data.startswith(b"%PDF-"):
        raise PDFError("The attachment isn't a PDF.")
    return data


@dataclass(frozen=True)
class Command:
    action: Literal["approve", "reject", "retry"]
    note: str


_COMMAND = re.compile(r"^\s*/(approve|reject|retry)\b[ \t]*(.*)\Z", re.IGNORECASE | re.DOTALL)


def parse_command(text: str | None) -> Command | None:
    m = _COMMAND.match(text or "")
    if not m:
        return None
    note = " ".join(m.group(2).split())[:500]
    return Command(action=m.group(1).lower(), note=note)  # type: ignore[arg-type]
