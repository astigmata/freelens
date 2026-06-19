"""Shared helpers that turn raw Kubernetes objects into display strings.

Previously this logic was copy-pasted across every ``get_*`` function; centralising
it keeps the resource registry declarative and the formatting consistent.
"""

import datetime


def _now(tzinfo) -> datetime.datetime:
    return datetime.datetime.now(tzinfo)


def age_short(creation_timestamp) -> str:
    """Compact age, Lens-style: ``3d`` / ``5h`` / ``4m12s`` / ``8s``.

    Below an hour the value is shown in minutes and seconds (and just seconds
    below a minute), which is far more useful for freshly-created pods.
    """
    if creation_timestamp is None:
        return "N/A"
    age = _now(creation_timestamp.tzinfo) - creation_timestamp
    total = max(int(age.total_seconds()), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d"
    if hours > 0:
        return f"{hours}h"
    if minutes > 0:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def age_long(creation_timestamp) -> str:
    """Verbose age, e.g. ``3d 4h 12m ago`` (detail panel)."""
    if creation_timestamp is None:
        return "N/A"
    age = _now(creation_timestamp.tzinfo) - creation_timestamp
    total = int(age.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{days}d {hours}h {minutes}m ago"


def created_at(creation_timestamp) -> str:
    if creation_timestamp is None:
        return "N/A"
    return creation_timestamp.strftime("%Y-%m-%dT%H:%M:%S%z")


def owner_ref(metadata) -> str:
    """``Kind/name`` of the first owner reference, or ``N/A``."""
    refs = metadata.owner_references
    if not refs:
        return "N/A"
    return f"{refs[0].kind}/{refs[0].name}"


def key_value_pairs(mapping) -> list[str]:
    """Sorted ``key: value`` lines from a labels/annotations dict."""
    if not mapping:
        return ["N/A"]
    return [f"{k}: {v}" for k, v in sorted(mapping.items())]


def joined_labels(mapping) -> str:
    if not mapping:
        return "N/A"
    return ", ".join(f"{k}={v}" for k, v in sorted(mapping.items()))
