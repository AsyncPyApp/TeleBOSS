"""App thin-main, BuildInCommands, offline handler probes."""

from __future__ import annotations

import ast
import builtins
import dis
import importlib

from helpers import (
    BUILDIN_EXPECTED_KEYS,
    CALLBACK_PROBE_ORDER,
    HANDLER_CB_COUNT,
    HANDLER_MSG_COUNT,
    REPO_ROOT,
    SHIM_MODS,
    module_imports,
)

HOST_COMMAND_METHODS = frozenset(
    {
        "add_answer",
        "mail",
        "status",
        "random_msg",
        "pardon",
        "get_id",
        "help_msg",
        "mute_user",
        "revoke",
        "cremate",
        "calc",
        "start",
        "overview",
        "version",
        "plugins",
        "git",
        "niko",
    }
)
PREVOTE_STUB_METHODS = frozenset(
    {
        "add_usr",
        "ban_usr",
        "kick_usr",
        "mute_usr",
        "unban_usr",
        "thresholds",
        "timer",
        "rate",
        "whitelist",
        "delete_msg",
        "clear_msg",
        "private_mode",
        "op",
        "rem_topic",
        "rank",
        "deop",
        "title",
        "description",
        "chat_pic",
        "allies_list",
        "shield",
        "rules_msg",
        "custom_poll",
        "votes",
        "marmalade",
    }
)


class _FakeCall:
    def __init__(self, data: str):
        self.data = data


def _filter_matches(handler_dict: dict, data: str) -> bool:
    filters = handler_dict.get("filters") or {}
    func = filters.get("func")
    if func is None:
        func = handler_dict.get("func")
    if func is None:
        return False
    try:
        return bool(func(_FakeCall(data)))
    except Exception:
        return False


_HOST_COMMANDS_PKG = REPO_ROOT / "src/teleboss/app/host_commands"
_HOST_COMMANDS_MIXINS = (
    "membership.py",
    "info.py",
    "moderation.py",
    "misc.py",
)
# Indicative mixin homes from T02 (must stay disjoint and cover HOST_COMMAND_METHODS).
_HOST_COMMAND_HOMES: dict[str, frozenset[str]] = {
    "membership.py": frozenset({"add_answer"}),
    "info.py": frozenset(
        {"status", "overview", "version", "plugins", "git", "help_msg", "get_id", "start"}
    ),
    "moderation.py": frozenset({"mute_user", "pardon", "revoke", "cremate"}),
    "misc.py": frozenset({"mail", "random_msg", "calc", "niko"}),
}


def test_thin_main_py() -> None:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    main_tree = ast.parse(main_src)
    assert not any(
        isinstance(n, ast.ClassDef) and n.name == "BuildInCommands" for n in main_tree.body
    )
    assert not any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.decorator_list
        for n in main_tree.body
    )
    assert not (REPO_ROOT / "src/teleboss/app/host_commands.py").exists()
    assert (_HOST_COMMANDS_PKG / "__init__.py").is_file()
    for name in _HOST_COMMANDS_MIXINS:
        assert (_HOST_COMMANDS_PKG / name).is_file(), name
    for rel in (
        "src/teleboss/app/commands.py",
        "src/teleboss/app/handlers/membership.py",
        "src/teleboss/app/handlers/captcha.py",
        "src/teleboss/app/handlers/votes.py",
        "src/teleboss/app/handlers/op.py",
        "src/teleboss/app/handlers/help.py",
    ):
        assert (REPO_ROOT / rel).is_file(), rel

    cmds_src = (REPO_ROOT / "src/teleboss/app/commands.py").read_text(encoding="utf-8")
    assert "from teleboss.app.host_commands import HostCommands" in cmds_src


def test_buildin_commands_keys_and_aliases(teleboss_runtime) -> None:
    from teleboss.app.commands import BuildInCommands

    cmds = BuildInCommands().built_in_commands_dict
    assert len(cmds) == len(BUILDIN_EXPECTED_KEYS)
    assert set(cmds) == set(BUILDIN_EXPECTED_KEYS)
    for k, expected_alias in BUILDIN_EXPECTED_KEYS.items():
        assert cmds[k].aliases == expected_alias, k

    cmds_ast = ast.parse((REPO_ROOT / "src/teleboss/app/commands.py").read_text(encoding="utf-8"))
    class_def = next(
        n for n in cmds_ast.body if isinstance(n, ast.ClassDef) and n.name == "BuildInCommands"
    )
    assert any(isinstance(b, ast.Name) and b.id == "HostCommands" for b in class_def.bases)
    init = next(n for n in class_def.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    keys_from_ast: list[str] = []
    for stmt in init.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Attribute) and t.attr == "built_in_commands_dict":
                    if isinstance(stmt.value, ast.Dict):
                        for k in stmt.value.keys:
                            if isinstance(k, ast.Constant):
                                keys_from_ast.append(k.value)
    assert set(keys_from_ast) == set(cmds)


def test_host_commands_method_homes_and_dag() -> None:
    assert len(HOST_COMMAND_METHODS) == 17
    home_union = set().union(*_HOST_COMMAND_HOMES.values())
    assert home_union == HOST_COMMAND_METHODS
    seen: set[str] = set()
    for methods in _HOST_COMMAND_HOMES.values():
        assert methods.isdisjoint(seen), methods & seen
        seen |= methods

    init_path = _HOST_COMMANDS_PKG / "__init__.py"
    cmds_path = REPO_ROOT / "src/teleboss/app/commands.py"
    init_ast = ast.parse(init_path.read_text(encoding="utf-8"))
    cmds_ast = ast.parse(cmds_path.read_text(encoding="utf-8"))

    host_cls = next(n for n in init_ast.body if isinstance(n, ast.ClassDef) and n.name == "HostCommands")
    assert {b.id for b in host_cls.bases if isinstance(b, ast.Name)} == {
        "MembershipMixin",
        "InfoMixin",
        "ModerationMixin",
        "MiscMixin",
    }
    assert not any(isinstance(n, ast.FunctionDef) for n in host_cls.body)

    host_methods: set[str] = set()
    for name in _HOST_COMMANDS_MIXINS:
        mixin_ast = ast.parse((_HOST_COMMANDS_PKG / name).read_text(encoding="utf-8"))
        mixin_methods: set[str] = set()
        for node in mixin_ast.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Mixin"):
                mixin_methods.update(
                    n.name for n in node.body if isinstance(n, ast.FunctionDef)
                )
        assert mixin_methods == _HOST_COMMAND_HOMES[name], name
        host_methods |= mixin_methods
    assert host_methods == HOST_COMMAND_METHODS

    from teleboss.app.host_commands import HostCommands

    for method_name in HOST_COMMAND_METHODS:
        assert hasattr(HostCommands, method_name), method_name
        assert callable(getattr(HostCommands, method_name)), method_name

    cmds_cls = next(n for n in cmds_ast.body if isinstance(n, ast.ClassDef) and n.name == "BuildInCommands")
    stub_methods = {
        n.name for n in cmds_cls.body if isinstance(n, ast.FunctionDef) and n.name != "__init__"
    }
    assert stub_methods == PREVOTE_STUB_METHODS
    assert host_methods.isdisjoint(stub_methods)

    package_paths = [init_path, *(_HOST_COMMANDS_PKG / name for name in _HOST_COMMANDS_MIXINS)]
    imports: set[str] = set()
    for path in package_paths:
        imports |= module_imports(path)
    assert not any(m == "teleboss.domain" or m.startswith("teleboss.domain.") for m in imports)
    assert imports.isdisjoint(SHIM_MODS)
    assert "teleboss.app.commands" not in imports
    allowed_prefixes = (
        "teleboss.shared.",
        "teleboss.voting.",
        "teleboss.app.host_commands.",
    )
    for mod in imports:
        if mod.startswith("teleboss."):
            assert any(mod == p.rstrip(".") or mod.startswith(p) for p in allowed_prefixes), mod


def test_host_commands_mixin_load_globals_bound() -> None:
    """Each mixin method's LOAD_GLOBAL names must resolve on its defining module.

    Catches missing imports after package split (e.g. ``time.time()`` without ``import time``).
    """
    mixin_modules = (
        "teleboss.app.host_commands.membership",
        "teleboss.app.host_commands.info",
        "teleboss.app.host_commands.moderation",
        "teleboss.app.host_commands.misc",
    )
    for mod_name in mixin_modules:
        mod = importlib.import_module(mod_name)
        mixin_cls = next(
            v for v in vars(mod).values() if isinstance(v, type) and v.__name__.endswith("Mixin")
        )
        for attr_name, attr in vars(mixin_cls).items():
            if attr_name.startswith("_"):
                continue
            raw = attr.__func__ if isinstance(attr, staticmethod) else attr
            if not callable(raw) or not hasattr(raw, "__code__"):
                continue
            for instr in dis.get_instructions(raw):
                if instr.opname != "LOAD_GLOBAL":
                    continue
                name = instr.argval
                if isinstance(name, tuple):
                    name = name[0]
                if name in ("__build_class__", "super") or hasattr(builtins, name):
                    continue
                assert name in mod.__dict__, (
                    f"{mod_name}.{attr_name} LOAD_GLOBAL {name!r} not bound "
                    f"(missing import in mixin module?)"
                )


def test_handler_bot_identity_and_shared_callables(teleboss_runtime) -> None:
    import main  # noqa: F401 — registers handlers
    from teleboss.app.handlers import captcha as captcha_mod
    from teleboss.app.handlers import help as help_mod
    from teleboss.app.handlers import membership as membership_mod
    from teleboss.app.handlers import op as op_mod
    from teleboss.app.handlers import votes as votes_mod
    from teleboss.voting.engine import poll_engine as pe_canon

    assert membership_mod.bot is teleboss_runtime.bot
    assert captcha_mod.bot is teleboss_runtime.bot
    assert votes_mod.bot is teleboss_runtime.bot
    assert op_mod.bot is teleboss_runtime.bot
    assert help_mod.bot is teleboss_runtime.bot
    assert votes_mod.poll_engine is pe_canon
    assert op_mod.poll_engine is pe_canon
    assert op_mod.close_vote is votes_mod.close_vote
    assert op_mod.call_msg_chk is votes_mod.call_msg_chk


def test_offline_handler_counts_and_order(teleboss_runtime) -> None:
    import main  # noqa: F401

    msg_handlers = list(getattr(teleboss_runtime.bot, "message_handlers", []))
    cb_handlers = list(getattr(teleboss_runtime.bot, "callback_query_handlers", []))
    assert len(msg_handlers) == HANDLER_MSG_COUNT, f"got {len(msg_handlers)}"
    assert len(cb_handlers) == HANDLER_CB_COUNT, f"got {len(cb_handlers)}"
    assert CALLBACK_PROBE_ORDER.index("op!_close") < CALLBACK_PROBE_ORDER.index("vote!_yes")

    for i, probe in enumerate(CALLBACK_PROBE_ORDER):
        matches = [j for j, h in enumerate(cb_handlers) if _filter_matches(h, probe)]
        assert matches and matches[0] == i, f"probe {probe!r}: matches={matches}, want first={i}"

    mh = msg_handlers[0]
    mh_filters = mh.get("filters") or {}
    ct = mh_filters.get("content_types") or mh.get("content_types")
    assert ct == ["new_chat_members"] or ct == "new_chat_members"

    op_idx = next(i for i, h in enumerate(cb_handlers) if _filter_matches(h, "op!_x"))
    vote_idx = next(i for i, h in enumerate(cb_handlers) if _filter_matches(h, "vote!_x"))
    assert op_idx < vote_idx


def test_votes_mid_import_order() -> None:
    votes_src = (REPO_ROOT / "src/teleboss/app/handlers/votes.py").read_text(encoding="utf-8")
    assert "from teleboss.app.handlers import op" in votes_src
    vote_pos = votes_src.find('func=lambda call: "vote!" in call.data')
    op_import_pos = votes_src.find("from teleboss.app.handlers import op")
    assert 0 <= op_import_pos < vote_pos


def test_callback_tokens_and_op_before_vote_unchanged(teleboss_runtime) -> None:
    """Exact callback-token probes and op! registration before vote! (T03)."""
    import main  # noqa: F401

    cb_handlers = list(getattr(teleboss_runtime.bot, "callback_query_handlers", []))
    for i, probe in enumerate(CALLBACK_PROBE_ORDER):
        matches = [j for j, h in enumerate(cb_handlers) if _filter_matches(h, probe)]
        assert matches and matches[0] == i, f"probe {probe!r}: matches={matches}"

    op_idx = next(i for i, h in enumerate(cb_handlers) if _filter_matches(h, "op!_x"))
    vote_idx = next(i for i, h in enumerate(cb_handlers) if _filter_matches(h, "vote!_x"))
    assert op_idx < vote_idx


def test_handler_sources_forbid_legacy_poll_apis() -> None:
    """votes/op/host must not call get_poll or update_poll_votes (AST gate)."""
    forbidden = frozenset({"get_poll", "update_poll_votes"})
    paths = [
        REPO_ROOT / "src/teleboss/app/handlers/votes.py",
        REPO_ROOT / "src/teleboss/app/handlers/op.py",
        *(_HOST_COMMANDS_PKG / name for name in ("__init__.py", *_HOST_COMMANDS_MIXINS)),
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        hit = called & forbidden
        assert not hit, f"{path.relative_to(REPO_ROOT).as_posix()} still calls {sorted(hit)}"
