"""Prevote class map / inheritance / identity (no HEAD AST move-only)."""

from __future__ import annotations

import ast
import importlib

from helpers import (
    PREVOTE_DOMAIN_CLASS_MAP,
    PREVOTE_EXPECTED_CLASSES,
    PREVOTE_INHERITANCE,
    REPO_ROOT,
)

# T04 binding: sibling prevote_*.py under split domains; allies/content stay unsplit.
PREVOTE_SIBLING_FILES = {
    "settings": {
        "prevote_thresholds.py",
        "prevote_timer.py",
        "prevote_rating.py",
        "prevote_whitelist.py",
        "prevote_modes.py",
        "prevote_protection.py",
    },
    "moderation": {
        "prevote_ban.py",
        "prevote_messages.py",
        "prevote_invite.py",
        "prevote_join.py",
    },
    "admin": {
        "prevote_op.py",
        "prevote_roles.py",
        "prevote_chat_meta.py",
    },
}


def test_expected_map_and_inheritance_colocated() -> None:
    assert len(PREVOTE_EXPECTED_CLASSES) == 28
    mapped = [c for classes in PREVOTE_DOMAIN_CLASS_MAP.values() for c in classes]
    assert len(mapped) == 28 and len(set(mapped)) == 28
    assert set(mapped) == set(PREVOTE_EXPECTED_CLASSES)
    settings = PREVOTE_DOMAIN_CLASS_MAP["teleboss.domain.settings.prevote"]
    assert "Shield" in settings and "Whitelist" in settings
    for child, parent in PREVOTE_INHERITANCE.items():
        same = any(child in classes and parent in classes for classes in PREVOTE_DOMAIN_CLASS_MAP.values())
        assert same, f"{child}/{parent}"


def test_domain_prevote_files_exist() -> None:
    for domain in ("moderation", "settings", "admin", "allies", "content"):
        path = REPO_ROOT / "teleboss" / "domain" / domain / "prevote.py"
        assert path.is_file(), domain


def test_prevote_sibling_split_binding() -> None:
    for domain, expected in PREVOTE_SIBLING_FILES.items():
        actual = {
            p.name
            for p in (REPO_ROOT / "teleboss" / "domain" / domain).glob("prevote_*.py")
        }
        assert actual == expected, domain
    for domain in ("allies", "content"):
        siblings = list((REPO_ROOT / "teleboss" / "domain" / domain).glob("prevote_*.py"))
        assert not siblings, domain


def test_prevote_barrels_are_thin_reexports() -> None:
    for domain in ("settings", "moderation", "admin"):
        path = REPO_ROOT / "teleboss" / "domain" / domain / "prevote.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        class_defs = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        assert not class_defs, f"{domain} barrel still defines {class_defs}"
        exported = PREVOTE_DOMAIN_CLASS_MAP[f"teleboss.domain.{domain}.prevote"]
        all_node = next(
            (
                n
                for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
            ),
            None,
        )
        assert all_node is not None, domain
        assert isinstance(all_node.value, ast.List)
        names = [elt.value for elt in all_node.value.elts if isinstance(elt, ast.Constant)]
        assert names == exported, domain


def test_domain_prevote_classes_and_inheritance(teleboss_runtime) -> None:
    for name in PREVOTE_EXPECTED_CLASSES:
        found = False
        for mod_name, class_names in PREVOTE_DOMAIN_CLASS_MAP.items():
            if name not in class_names:
                continue
            mod = importlib.import_module(mod_name)
            assert hasattr(mod, name), f"{mod_name}.{name}"
            found = True
            break
        assert found, name

    moderation = importlib.import_module("teleboss.domain.moderation.prevote")
    admin = importlib.import_module("teleboss.domain.admin.prevote")
    assert issubclass(moderation.Kick, moderation.Ban)
    assert issubclass(moderation.MessageSilentRemover, moderation.MessageRemover)
    assert issubclass(admin.OpGlobal, admin.Op)
    assert getattr(moderation.Ban, "vote_type", None) == "ban"
