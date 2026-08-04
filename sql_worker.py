"""Compatibility shim: canonical module is teleboss.shared.storage.sql_worker."""
from teleboss.shared.storage.sql_worker import SQLWrapper, SqlWorker

__all__ = ["SQLWrapper", "SqlWorker"]
