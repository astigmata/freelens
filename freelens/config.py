"""Application settings, overridable via environment variables."""

import os

HOST = os.environ.get("FREELENS_HOST", "127.0.0.1")
PORT = int(os.environ.get("FREELENS_PORT", "8050"))
DEBUG = os.environ.get("FREELENS_DEBUG", "false").lower() == "true"

# Page size for resource tables.
TABLE_PAGE_SIZE = int(os.environ.get("FREELENS_TABLE_PAGE_SIZE", "15"))

# Extra browser origins (scheme://host[:port]) allowed to open the pod-terminal
# WebSocket, on top of same-origin requests. Comma-separated. Used to defend the
# /ws/exec endpoint against Cross-Site WebSocket Hijacking. Empty = same-origin
# only, which is the right default.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("FREELENS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
