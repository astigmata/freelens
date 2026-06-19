"""Application settings, overridable via environment variables."""

import os

HOST = os.environ.get("FREELENS_HOST", "127.0.0.1")
PORT = int(os.environ.get("FREELENS_PORT", "8050"))
DEBUG = os.environ.get("FREELENS_DEBUG", "false").lower() == "true"

# Page size for resource tables.
TABLE_PAGE_SIZE = int(os.environ.get("FREELENS_TABLE_PAGE_SIZE", "15"))
