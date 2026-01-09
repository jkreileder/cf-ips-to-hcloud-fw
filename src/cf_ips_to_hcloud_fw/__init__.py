from __future__ import annotations

from importlib import metadata

try:  # noqa: RUF067
    __version__ = metadata.version("cf-ips-to-hcloud-fw")
except metadata.PackageNotFoundError:
    __version__ = "local"

__all__ = ["__version__"]
