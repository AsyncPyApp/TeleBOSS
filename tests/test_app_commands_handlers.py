"""App thin-main, BuildInCommands, offline handler probes."""

from __future__ import annotations

import ast

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
    assert (REPO_ROOT / "teleboss/app/host_commands.py").is_file()
    for rel in (
        "teleboss/app/commands.py",
        "teleboss/app/host_commands.py",
        "teleboss/app/handlers/membership.py",
        "teleboss/app/handlers/captcha.py",
        "teleboss/app/handlers/votes.py",
        "teleboss/app/handlers/op.py",
        "teleboss/app/handlers/help.py",
    ):
        assert (REPO_ROOT / rel).is_file(), rel

    cmds_src = (REPO_ROOT / "teleboss/app/commands.py").read_text(encoding="utf-8")
    assert "from teleboss.app.host_commands import HostCommands" in cmds_src


def test_buildin_commands_keys_and_aliases(utils_mod) -> None:
    from teleboss.app.commands import BuildInCommands

    cmds = BuildInCommands().built_in_commands_dict
    assert len(cmds) == len(BUILDIN_EXPECTED_KEYS)
    assert set(cmds) == set(BUILDIN_EXPECTED_KEYS)
    for k, expected_alias in BUILDIN_EXPECTED_KEYS.items():
        assert cmds[k].aliases == expected_alias, k

    cmds_ast = ast.parse((REPO_ROOT / "teleboss/app/commands.py").read_text(encoding="utf-8"))
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
    host_path = REPO_ROOT / "teleboss/app/host_commands.py"
    cmds_path = REPO_ROOT / "teleboss/app/commands.py"
    host_ast = ast.parse(host_path.read_text(encoding="utf-8"))
    cmds_ast = ast.parse(cmds_path.read_text(encoding="utf-8"))

    host_cls = next(n for n in host_ast.body if isinstance(n, ast.ClassDef) and n.name == "HostCommands")
    host_methods = {n.name for n in host_cls.body if isinstance(n, ast.FunctionDef)}
    assert host_methods == HOST_COMMAND_METHODS

    cmds_cls = next(n for n in cmds_ast.body if isinstance(n, ast.ClassDef) and n.name == "BuildInCommands")
    stub_methods = {
        n.name for n in cmds_cls.body if isinstance(n, ast.FunctionDef) and n.name != "__init__"
    }
    assert stub_methods == PREVOTE_STUB_METHODS
    assert host_methods.isdisjoint(stub_methods)

    imports = module_imports(host_path)
    assert not any(m == "teleboss.domain" or m.startswith("teleboss.domain.") for m in imports)
    assert imports.isdisjoint(SHIM_MODS)
    assert "teleboss.app.commands" not in imports
    allowed_prefixes = ("teleboss.shared.", "teleboss.voting.")
    for mod in imports:
        if mod.startswith("teleboss."):
            assert any(mod == p.rstrip(".") or mod.startswith(p) for p in allowed_prefixes), mod


def test_handler_bot_identity_and_shared_callables(utils_mod) -> None:
    import main  # noqa: F401 — registers handlers
    from teleboss.app.handlers import captcha as captcha_mod
    from teleboss.app.handlers import help as help_mod
    from teleboss.app.handlers import membership as membership_mod
    from teleboss.app.handlers import op as op_mod
    from teleboss.app.handlers import votes as votes_mod
    from teleboss.voting.engine import poll_engine as pe_canon

    assert membership_mod.bot is utils_mod.bot
    assert captcha_mod.bot is utils_mod.bot
    assert votes_mod.bot is utils_mod.bot
    assert op_mod.bot is utils_mod.bot
    assert help_mod.bot is utils_mod.bot
    assert votes_mod.poll_engine is pe_canon
    assert op_mod.poll_engine is pe_canon
    assert op_mod.close_vote is votes_mod.close_vote
    assert op_mod.call_msg_chk is votes_mod.call_msg_chk


def test_offline_handler_counts_and_order(utils_mod) -> None:
    import main  # noqa: F401

    msg_handlers = list(getattr(utils_mod.bot, "message_handlers", []))
    cb_handlers = list(getattr(utils_mod.bot, "callback_query_handlers", []))
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
    votes_src = (REPO_ROOT / "teleboss/app/handlers/votes.py").read_text(encoding="utf-8")
    assert "from teleboss.app.handlers import op" in votes_src
    vote_pos = votes_src.find('func=lambda call: "vote!" in call.data')
    op_import_pos = votes_src.find("from teleboss.app.handlers import op")
    assert 0 <= op_import_pos < vote_pos
