"""T01: SqlWorker facade composition, public re-exports, and mixin method freeze."""

from __future__ import annotations

import ast
import inspect

from helpers import REPO_ROOT, assert_soft_version_order, module_imports

_STORAGE = REPO_ROOT / "src/shared/storage"

# Concern modules that must hold logic after the monolith split (T01).
_CONCERN_MODULES = (
    "poll_types.py",
    "sql_connection.py",
    "poll_schema.py",
    "poll_repository.py",
    "host_tables.py",
)

# Host-facing SqlWorker callables that must remain on the composed class.
# Private helpers (_ensure_*, _fetch_*, …) are intentionally omitted.
_PUBLIC_METHOD_FREEZE = frozenset(
    {
        "abuse_check",
        "abuse_random",
        "abuse_remove",
        "abuse_update",
        "add_ally",
        "add_poll",
        "apply_vote",
        "captcha",
        "claim_completion",
        "clear_rate",
        "delete_completed",
        "get_all_polls",
        "get_all_rates",
        "get_allies",
        "get_ally",
        "get_message_id",
        "get_open_poll",
        "get_poll",
        "get_poll_by_unique_id",
        "get_rate",
        "get_recoverable_polls",
        "mailing",
        "mailing_get_all",
        "mark_completed",
        "mark_failed",
        "marmalade_add",
        "marmalade_get",
        "marmalade_remove",
        "params",
        "rem_rec",
        "remove_ally",
        "requeue_for_retry",
        "update_poll_votes",
        "update_rate",
        "whitelist",
        "whitelist_get_all",
    }
)

_INTERNAL_STORAGE_MODULES = frozenset(
    {
        "teleboss.shared.storage.poll_types",
        "teleboss.shared.storage.sql_connection",
        "teleboss.shared.storage.poll_schema",
        "teleboss.shared.storage.poll_repository",
        "teleboss.shared.storage.host_tables",
    }
)


def test_concern_modules_exist_beside_facade() -> None:
    """Logic modules from the T01 split are present next to the facade."""
    assert (_STORAGE / "sql_worker.py").is_file()
    for name in _CONCERN_MODULES:
        assert (_STORAGE / name).is_file(), name


def test_facade_is_thin_mixin_composer() -> None:
    """``sql_worker.py`` only defines ``SqlWorker.__init__``; CRUD lives in mixins."""
    facade = _STORAGE / "sql_worker.py"
    tree = ast.parse(facade.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(classes) == 1
    sql_worker = classes[0]
    assert sql_worker.name == "SqlWorker"
    base_names = {
        b.id for b in sql_worker.bases if isinstance(b, ast.Name)
    }
    assert base_names == {
        "PollSchemaMixin",
        "PollRepositoryMixin",
        "HostTablesMixin",
    }
    methods = [
        n.name
        for n in sql_worker.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ["__init__"]
    # Facade stays thin; heavy logic modules must be larger than the facade.
    facade_lines = len(facade.read_text(encoding="utf-8").splitlines())
    assert facade_lines < 100, facade_lines
    for name in ("poll_schema.py", "poll_repository.py", "host_tables.py"):
        assert len((_STORAGE / name).read_text(encoding="utf-8").splitlines()) > facade_lines


def test_public_imports_from_facade_path() -> None:
    """Stable public symbols remain importable from ``sql_worker`` facade."""
    from teleboss.shared.storage import poll_types, sql_connection
    from teleboss.shared.storage.sql_worker import (
        ApplyVoteResult,
        ApplyVoteStatus,
        PollMigrationError,
        PollRow,
        SQLWrapper,
        SqlWorker,
        VoteMutator,
        __all__,
    )

    assert ApplyVoteResult is poll_types.ApplyVoteResult
    assert ApplyVoteStatus is poll_types.ApplyVoteStatus
    assert PollMigrationError is poll_types.PollMigrationError
    assert PollRow is poll_types.PollRow
    assert VoteMutator is poll_types.VoteMutator
    assert SQLWrapper is sql_connection.SQLWrapper
    assert inspect.isclass(SqlWorker)
    expected_all = {
        "ApplyVoteResult",
        "ApplyVoteStatus",
        "PollMigrationError",
        "PollRow",
        "SQLWrapper",
        "SqlWorker",
        "VoteMutator",
    }
    assert set(__all__) == expected_all


def test_sql_worker_public_method_set_frozen() -> None:
    """Composed ``SqlWorker`` exposes the full host-facing method set."""
    from teleboss.shared.storage.sql_worker import SqlWorker

    present = {
        name
        for name, member in inspect.getmembers(SqlWorker, predicate=callable)
        if not name.startswith("_")
    }
    missing = sorted(_PUBLIC_METHOD_FREEZE - present)
    assert not missing, f"missing methods: {missing}"
    # No unexpected public callables beyond the freeze + object builtins we skip.
    extra = sorted(present - _PUBLIC_METHOD_FREEZE)
    # ``dbname`` is a class attribute, not returned by getmembers(..., callable).
    assert not extra, f"unexpected public callables: {extra}"


def test_poll_column_offsets_zero_through_ten_stable() -> None:
    """SELECT projection keeps legacy offsets 0–9 and state at offset 10."""
    from teleboss.shared.storage import poll_types

    columns = [c.strip() for c in poll_types._POLL_COLUMNS.replace("\n", " ").split(",")]
    assert columns == [
        "unique_id",
        "message_id",
        "type",
        "chat_id",
        "buttons",
        "timer",
        "data",
        "votes_need",
        "hidden",
        "thread_id",
        "state",
    ]
    assert columns.index("state") == 10


def test_product_callers_import_facade_not_internal_mixins() -> None:
    """Outside ``shared/storage``, product code must not import concern modules."""
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("src/shared/storage/"):
            continue
        for mod in module_imports(path):
            if mod in _INTERNAL_STORAGE_MODULES or any(
                mod.startswith(f"{m}.") for m in _INTERNAL_STORAGE_MODULES
            ):
                offenders.append(f"{rel}:{mod}")
    assert not offenders, offenders


def test_t01_keeps_soft_configdata_version_order(runtime_data) -> None:
    """Structural facade work must not break soft MIN_VERSION ≤ VERSION order."""
    assert_soft_version_order(runtime_data.MIN_VERSION, runtime_data.VERSION)
