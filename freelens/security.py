"""HTTP security headers applied to every response.

These are defence-in-depth headers that do not change behaviour but harden the
app against clickjacking, MIME sniffing and referrer leakage. A strict
Content-Security-Policy is *not* set globally because the Dash runtime relies on
inline configuration; the high-risk ``/terminal`` page sets its own locked-down
CSP in :mod:`freelens.terminal`.
"""

from flask import Flask

_HEADERS = {
    # Disallow framing by other origins (clickjacking). The app frames its own
    # /terminal page, which SAMEORIGIN still permits.
    "X-Frame-Options": "SAMEORIGIN",
    # Stop browsers from MIME-sniffing responses into a different content type.
    "X-Content-Type-Options": "nosniff",
    # Don't leak the (possibly sensitive) URL to third parties.
    "Referrer-Policy": "no-referrer",
    # Force HTTPS once seen over TLS (no effect on plain HTTP). HDS deployments
    # must terminate TLS in front of the app.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def register_security_headers(server: Flask) -> None:
    """Attach the static security headers to every response on ``server``."""

    @server.after_request
    def _set_headers(response):
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
