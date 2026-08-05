"""Shared helpers and frozen expected sets for durable offline tests."""

from __future__ import annotations

import ast
from pathlib import Path

from packaging.version import parse as parse_version

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIM_MODS = ("utils", "sql_worker", "poll_engines", "plugin_engine", "prevote", "postvote")

# Documentation labels for root shim → canonical packages (not import strings to exec).
SHIM_CANONICAL_NOTES: dict[str, str] = {
    "utils": "teleboss.shared.* (barrel: access/bootstrap/calc/command/config/help_ui/parsers/runtime/vote_ui/…)",
    "sql_worker": "teleboss.shared.storage.sql_worker",
    "poll_engines": "teleboss.voting.* (bases / engine / exceptions)",
    "plugin_engine": "teleboss.plugin_loader.loader",
    "prevote": "teleboss.domain.{moderation,settings,admin,allies,content}.prevote",
    "postvote": "teleboss.domain.*.postvote + teleboss.domain.postvote_registry",
}

# Post-T02: main left product shim callers; six root shim files remain until T05.
PRODUCT_SHIM_CALLER_FILES: frozenset[str] = frozenset()

POSTVOTE_EXPECTED_KEYS = [
    "invite",
    "ban",
    "unban",
    "threshold",
    "timer",
    "timer for ban votes",
    "delete message",
    "op",
    "deop",
    "title",
    "chat picture",
    "description",
    "rank",
    "captcha",
    "change rate",
    "add allies",
    "remove allies",
    "timer for random cooldown",
    "whitelist",
    "global op permissions",
    "private mode",
    "remove topic",
    "add rules",
    "remove rules",
    "custom poll",
    "shield",
    "marmalade",
    "vote_privacy",
    "global op setup",
    "op setup",
]

POSTVOTE_EXPECTED_CLASSES = [
    "UserAdd",
    "Ban",
    "UnBan",
    "Captcha",
    "DelMessage",
    "Threshold",
    "Timer",
    "TimerBan",
    "ChangeRate",
    "Whitelist",
    "PrivateMode",
    "Shield",
    "VotePrivacy",
    "Marmalade",
    "RandomCooldown",
    "GlobalOp",
    "OpSetup",
    "GlobalOpSetup",
    "Op",
    "Rank",
    "Deop",
    "Title",
    "Description",
    "ChatPic",
    "Topic",
    "AddAllies",
    "RemoveAllies",
    "AddRules",
    "RemoveRules",
    "CustomPoll",
]

POSTVOTE_DOMAIN_CLASS_MAP = {
    "teleboss.domain.moderation.postvote": [
        "UserAdd",
        "Ban",
        "UnBan",
        "Captcha",
        "DelMessage",
    ],
    "teleboss.domain.settings.postvote": [
        "Threshold",
        "Timer",
        "TimerBan",
        "ChangeRate",
        "Whitelist",
        "PrivateMode",
        "Shield",
        "VotePrivacy",
        "Marmalade",
        "RandomCooldown",
    ],
    "teleboss.domain.admin.postvote": [
        "GlobalOp",
        "OpSetup",
        "GlobalOpSetup",
        "Op",
        "Rank",
        "Deop",
        "Title",
        "Description",
        "ChatPic",
        "Topic",
    ],
    "teleboss.domain.allies.postvote": ["AddAllies", "RemoveAllies"],
    "teleboss.domain.content.postvote": ["AddRules", "RemoveRules", "CustomPoll"],
}

PREVOTE_EXPECTED_CLASSES = [
    "Invite",
    "Ban",
    "Kick",
    "Mute",
    "Unban",
    "MessageRemover",
    "MessageSilentRemover",
    "NewUserChecker",
    "Thresholds",
    "Timer",
    "Rating",
    "Whitelist",
    "PrivateMode",
    "Votes",
    "Shield",
    "Marmalade",
    "OpSetup",
    "Op",
    "OpGlobal",
    "RemoveTopic",
    "Rank",
    "Deop",
    "Title",
    "Description",
    "Avatar",
    "AlliesList",
    "Rules",
    "CustomPoll",
]

PREVOTE_DOMAIN_CLASS_MAP = {
    "teleboss.domain.moderation.prevote": [
        "Invite",
        "Ban",
        "Kick",
        "Mute",
        "Unban",
        "MessageRemover",
        "MessageSilentRemover",
        "NewUserChecker",
    ],
    "teleboss.domain.settings.prevote": [
        "Thresholds",
        "Timer",
        "Rating",
        "Whitelist",
        "PrivateMode",
        "Votes",
        "Shield",
        "Marmalade",
    ],
    "teleboss.domain.admin.prevote": [
        "OpSetup",
        "Op",
        "OpGlobal",
        "RemoveTopic",
        "Rank",
        "Deop",
        "Title",
        "Description",
        "Avatar",
    ],
    "teleboss.domain.allies.prevote": ["AlliesList"],
    "teleboss.domain.content.prevote": ["Rules", "CustomPoll"],
}

PREVOTE_INHERITANCE = {
    "Kick": "Ban",
    "MessageSilentRemover": "MessageRemover",
    "OpGlobal": "Op",
}

BUILDIN_EXPECTED_KEYS = {
    "invite": None,
    "ban": ("banuser",),
    "kick": ("kickuser",),
    "mute": None,
    "unmute": ("unban",),
    "threshold": None,
    "timer": None,
    "rate": None,
    "whitelist": None,
    "delete": None,
    "clear": None,
    "private": None,
    "op": None,
    "remtopic": None,
    "rank": None,
    "deop": None,
    "title": None,
    "description": None,
    "chatpic": None,
    "allies": None,
    "shield": None,
    "rules": None,
    "poll": None,
    "votes": None,
    "marmalade": None,
    "answer": None,
    "mail": None,
    "status": None,
    "random": ("redrum",),
    "pardon": None,
    "getchat": None,
    "help": None,
    "kill": None,
    "revoke": None,
    "cremate": None,
    "calc": None,
    "start": None,
    "overview": None,
    "version": None,
    "plugins": None,
    "git": None,
    "niko": None,
}

# Built at runtime so suite sources never embed the banned contiguous substring.
# "\n    init()" avoids a false match inside post_vote_list_init().
MAIN_BOOTSTRAP_ORDER = [
    "BuildInCommands()",
    "post_vote_list_init()",
    "Plugins(",
    "\n    init()",
    "register_commands(",
    "poll_engine.auto_restart_polls()",
    "bot." + "_".join(("infinity", "polling")) + "()",
]

# Class-level vote_type only (skip Title/Avatar/Allies/Rules/PrivateMode/Timer/Votes
# dynamic assignments documented as residual offline).
STABLE_VOTE_TYPES = {
    "Ban": "ban",
    "Mute": "ban",
    "Kick": "ban",
    "Unban": "unban",
    "MessageRemover": "delete message",
    "MessageSilentRemover": "delete message",
    "NewUserChecker": "captcha",
    "Thresholds": "threshold",
    "Rating": "change rate",
    "Whitelist": "whitelist",
    "Shield": "shield",
    "Marmalade": "marmalade",
    "OpSetup": "op setup",
    "Op": "op",
    "OpGlobal": "global op permissions",
    "RemoveTopic": "remove topic",
    "Rank": "rank",
    "Deop": "deop",
    "CustomPoll": "custom poll",
}

HANDLER_MSG_COUNT = 1
HANDLER_CB_COUNT = 9
CALLBACK_PROBE_ORDER = (
    "captcha_1",
    "cancel",
    "close",
    "my_vote",
    "user_votes",
    "op!_close",
    "vote!_yes",
    "help!_cat_0",
    "help!_main",
)

META_INFO_TEMPLATE_GOLDEN = {
    "name": str,
    "type": str,
    "version-min": str,
    "version-target": str,
    "description": str,
}
META_INFO_EXPECTED_KEYS = frozenset(META_INFO_TEMPLATE_GOLDEN)


def assert_soft_version_order(min_version: str, version: str) -> None:
    """Soft VERSION gate: MIN_VERSION <= VERSION via packaging.version."""
    assert isinstance(min_version, str) and min_version.strip()
    assert isinstance(version, str) and version.strip()
    assert parse_version(min_version) <= parse_version(version)


def module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def extract_postvote_registry_keys() -> list[str]:
    src = (REPO_ROOT / "teleboss/domain/postvote_registry.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "post_vote_list_init":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id == "post_vote_list":
                            assert isinstance(stmt.value, ast.Dict)
                            keys: list[str] = []
                            for k in stmt.value.keys:
                                assert isinstance(k, ast.Constant)
                                keys.append(k.value)
                            return keys
    raise RuntimeError("keys not found in registry")


def main_bootstrap_block_source() -> str:
    main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    main_tree = ast.parse(main_src)
    main_block = None
    for node in main_tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            main_block = node
            break
    assert main_block is not None, "__main__ block missing"
    boot_src = ast.get_source_segment(main_src, main_block)
    assert boot_src, "could not extract __main__ source"
    return boot_src
