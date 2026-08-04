"""Compatibility shim: canonical package is teleboss.plugin_loader."""
from teleboss.plugin_loader.loader import META_INFO_TEMPLATE, Plugins

__all__ = [
    "Plugins",
    "META_INFO_TEMPLATE",
]
