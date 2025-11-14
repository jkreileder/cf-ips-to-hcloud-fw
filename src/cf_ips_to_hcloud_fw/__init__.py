from __future__ import annotations

from importlib import metadata

try:
    __version__ = metadata.version("cf-ips-to-hcloud-fw")
except metadata.PackageNotFoundError:
    __version__ = "local"

__all__ = ["__version__"]
