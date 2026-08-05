"""Host-trusted plugin discovery and registration.

Supports config-driven modes ``directory``, ``entry_points``, and ``both``
(group ``teleboss.plugins``). Directory wins on meta-name conflict in ``both``.
"""

import fnmatch
import importlib
import logging
import os
import sys
import traceback
import types
from importlib import metadata as importlib_metadata

from packaging import version

from teleboss.shared.command import Command
from teleboss.shared.runtime import data
from teleboss.voting.engine import PollEngine

META_INFO_TEMPLATE = {
    'name': str,
    'type': str,
    'version-min': str,
    'version-target': str,
    'description': str
}

PLUGIN_ENTRY_POINT_GROUP = "teleboss.plugins"
VALID_PLUGINS_MODES = frozenset({"directory", "entry_points", "both"})


class Plugins:
    """Discover, validate, and register host-trusted plugins."""

    def __init__(self, built_in_commands_dict):
        """Load plugins according to ``data.plugins_mode``.

        Args:
            built_in_commands_dict: Mutable built-in command name to ``Command`` map.
        """
        plugins_dict = {}
        registered_cmd_by_plugins = {}
        loaded_meta_names = set()
        build_in_all_commands = self.get_all_prebuild_commands(built_in_commands_dict)
        built_in_commands_clear_dict = {
            i: j.command_func for i, j in built_in_commands_dict.items()
        }
        self.commands_final_dict = {}

        mode = getattr(data, "plugins_mode", "directory") or "directory"
        if mode not in VALID_PLUGINS_MODES:
            logging.warning(
                "Unknown plugins_mode %r; falling back to directory",
                mode,
            )
            mode = "directory"

        if mode in ("directory", "both"):
            self._load_directory_plugins(
                built_in_commands_dict,
                built_in_commands_clear_dict,
                build_in_all_commands,
                registered_cmd_by_plugins,
                plugins_dict,
                loaded_meta_names,
            )

        if mode in ("entry_points", "both"):
            self._load_entry_point_plugins(
                built_in_commands_dict,
                built_in_commands_clear_dict,
                build_in_all_commands,
                registered_cmd_by_plugins,
                plugins_dict,
                loaded_meta_names,
                skip_existing=(mode == "both"),
            )

        if plugins_dict:
            logging.info("Loaded plugins: " + ", ".join(plugins_dict.keys()))
            data.plugins = plugins_dict

    def _load_directory_plugins(
        self,
        built_in_commands_dict,
        built_in_commands_clear_dict,
        build_in_all_commands,
        registered_cmd_by_plugins,
        plugins_dict,
        loaded_meta_names,
    ):
        """Scan the host plugin directory and register valid modules.

        Args:
            built_in_commands_dict: Mutable built-in commands map.
            built_in_commands_clear_dict: Name to callable copy for Plugin ctors.
            build_in_all_commands: Flat list of built-in names and aliases.
            registered_cmd_by_plugins: Command name to plugin entry label.
            plugins_dict: Accumulator of loaded meta name to description.
            loaded_meta_names: Set of meta names already accepted.
        """
        abs_folder = self.resolve_plugin_directory()
        if abs_folder is None:
            return

        parent_dir = os.path.dirname(abs_folder)
        package_name = os.path.basename(abs_folder)
        path_inserted = False
        if parent_dir and parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
            path_inserted = True

        try:
            files_list = os.listdir(abs_folder)
            pattern = "*.py"
            for entry in files_list:
                if not fnmatch.fnmatch(entry, pattern):
                    continue
                if os.path.isdir(os.path.join(abs_folder, entry)):
                    continue
                plugin_name = entry.split(".")[0]
                file_path = os.path.join(abs_folder, entry)
                try:
                    if self.forbidden_dec_in_plug(file_path):
                        continue
                    plugin_class = importlib.import_module(
                        f'{package_name}.{plugin_name}'
                    ).Plugin(built_in_commands_clear_dict.copy())
                    # We can reference built-in functions in Teleboss using a copy of the list,
                    # but we do not allow breaking the original list.
                    accepted = self._accept_plugin_instance(
                        plugin_class,
                        entry,
                        built_in_commands_dict,
                        build_in_all_commands,
                        registered_cmd_by_plugins,
                        plugins_dict,
                        loaded_meta_names,
                        skip_if_name_loaded=False,
                    )
                    if accepted:
                        loaded_meta_names.add(plugin_class.meta_info['name'])
                except Exception as e:
                    logging.error(f'Module "{entry}" is invalid! The bot will close.')
                    logging.error(e)
                    logging.error(traceback.format_exc())
                    sys.exit(1)
        finally:
            if path_inserted:
                try:
                    sys.path.remove(parent_dir)
                except ValueError:
                    pass

    def _load_entry_point_plugins(
        self,
        built_in_commands_dict,
        built_in_commands_clear_dict,
        build_in_all_commands,
        registered_cmd_by_plugins,
        plugins_dict,
        loaded_meta_names,
        skip_existing,
    ):
        """Load plugins from ``teleboss.plugins`` entry points.

        Args:
            built_in_commands_dict: Mutable built-in commands map.
            built_in_commands_clear_dict: Name to callable copy for Plugin ctors.
            build_in_all_commands: Flat list of built-in names and aliases.
            registered_cmd_by_plugins: Command name to plugin entry label.
            plugins_dict: Accumulator of loaded meta name to description.
            loaded_meta_names: Set of meta names already accepted.
            skip_existing: When True, skip EP plugins whose meta name is loaded.
        """
        try:
            eps = importlib_metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        except Exception as e:
            logging.error(
                "Failed to enumerate entry points for group %r: %s",
                PLUGIN_ENTRY_POINT_GROUP,
                e,
            )
            return

        for ep in eps:
            entry_label = f"entry_point:{ep.name}"
            try:
                plugin_class = self._instantiate_from_entry_point(
                    ep,
                    built_in_commands_clear_dict,
                )
                if plugin_class is None:
                    continue
                mod_name = getattr(plugin_class, "__module__", "")
                mod = sys.modules.get(mod_name) if mod_name else None
                module_file = getattr(mod, "__file__", None) if mod is not None else None
                if module_file and self.forbidden_dec_in_plug(module_file):
                    continue
                accepted = self._accept_plugin_instance(
                    plugin_class,
                    entry_label,
                    built_in_commands_dict,
                    build_in_all_commands,
                    registered_cmd_by_plugins,
                    plugins_dict,
                    loaded_meta_names,
                    skip_if_name_loaded=skip_existing,
                )
                if accepted:
                    loaded_meta_names.add(plugin_class.meta_info['name'])
            except SystemExit:
                raise
            except Exception as e:
                logging.error(f'Module "{entry_label}" is invalid! The bot will close.')
                logging.error(e)
                logging.error(traceback.format_exc())
                sys.exit(1)

    def _instantiate_from_entry_point(self, ep, built_in_commands_clear_dict):
        """Resolve an entry point to a constructed Plugin instance.

        Args:
            ep: ``importlib.metadata.EntryPoint`` for group ``teleboss.plugins``.
            built_in_commands_clear_dict: Name to callable copy for Plugin ctors.

        Returns:
            Constructed plugin instance, or ``None`` when the target is unusable.
        """
        loaded = ep.load()
        plugin_ctor = None
        if isinstance(loaded, types.ModuleType):
            plugin_ctor = getattr(loaded, "Plugin", None)
            if plugin_ctor is None:
                logging.error(
                    'Entry point "%s" module has no Plugin attribute. '
                    'The plugin will not be loaded.',
                    ep.name,
                )
                return None
        elif isinstance(loaded, type):
            plugin_ctor = loaded
        else:
            logging.error(
                'Entry point "%s" did not resolve to a Plugin class/module. '
                'The plugin will not be loaded.',
                ep.name,
            )
            return None

        return plugin_ctor(built_in_commands_clear_dict.copy())

    def _accept_plugin_instance(
        self,
        plugin_class,
        entry,
        built_in_commands_dict,
        build_in_all_commands,
        registered_cmd_by_plugins,
        plugins_dict,
        loaded_meta_names,
        skip_if_name_loaded,
    ):
        """Validate meta/version/type and register commands for one plugin.

        Args:
            plugin_class: Constructed plugin instance.
            entry: Human-readable label for logs (filename or EP label).
            built_in_commands_dict: Mutable built-in commands map.
            build_in_all_commands: Flat list of built-in names and aliases.
            registered_cmd_by_plugins: Command name to plugin entry label.
            plugins_dict: Accumulator of loaded meta name to description.
            loaded_meta_names: Set of meta names already accepted.
            skip_if_name_loaded: When True, skip if meta name already loaded.

        Returns:
            True when the plugin was registered; False when skipped/rejected.
        """
        if not hasattr(plugin_class, 'meta_info'):
            logging.error(
                f'Plugin "{entry}" has no meta_info attribute. '
                f'The plugin will not be loaded.'
            )
            return False
        meta_info = plugin_class.meta_info
        if not self.meta_is_valid(meta_info, entry):
            return False

        meta_name = meta_info['name']
        if skip_if_name_loaded and meta_name in loaded_meta_names:
            logging.info(
                'Skipping entry point plugin "%s" (meta name %r already loaded '
                'from directory).',
                entry,
                meta_name,
            )
            return False

        if any([
            version.parse(meta_info['version-min']) > version.parse(data.VERSION),
            version.parse(meta_info['version-target']) < version.parse(data.VERSION),
        ]):
            logging.error(
                f'Plugin "{entry}" need bot version {meta_info["version-min"]} '
                f'- {meta_info["version-target"]}, current is {data.VERSION}. '
                f'The plugin will not be loaded.'
            )
            return False
        if meta_info['type'] not in ('simple', 'vote'):
            logging.error(
                f'Plugin "{entry}" have an incorrect type (must be "simple" or "vote"). '
                f'The plugin will not be loaded.'
            )
            return False
        if meta_info['type'] == 'vote':
            PollEngine.post_vote_list.update(plugin_class.vote_list)

        if hasattr(plugin_class, 'built_in_remove_list'):
            for rem_cmd in plugin_class.built_in_remove_list:
                if built_in_commands_dict.pop(rem_cmd, None):
                    logging.warning(
                        f'The "{entry}" plugin has disabled the built-in '
                        f'"{rem_cmd}" command.'
                    )
                else:
                    logging.error(
                        f'Plugin "{entry}" is trying to disable command "{rem_cmd}" '
                        'which has already been disabled or does not exist.'
                    )

        if not hasattr(plugin_class, 'plugin_commands_dict'):
            return False
        for command, command_data in plugin_class.plugin_commands_dict.items():
            if not (isinstance(command, str) and isinstance(command_data, Command)):
                logging.error(
                    f'Incorrect values in the plugin "{entry}" command list '
                    f'(key must be str, value must be a "Command" class). '
                    f'The bot will close.'
                )
                sys.exit(1)
            current_plugin_commands = [command]
            if command_data.aliases:
                current_plugin_commands.extend(command_data.aliases)
            for cmd in current_plugin_commands:
                registered_plugin_name = registered_cmd_by_plugins.get(cmd)
                if registered_plugin_name == entry:
                    logging.error(
                        f'Error in plugin "{entry}" - duplicate registration of '
                        f'"{cmd}" command detected. The bot will close.'
                    )
                    sys.exit(1)
                elif registered_plugin_name:
                    logging.error(
                        f'Conflicting commands in plugins - the command "{cmd}" '
                        f'has already been registered by another plugin '
                        f'"{registered_plugin_name}". The bot will close.'
                    )
                    sys.exit(1)
                registered_cmd_by_plugins.update({cmd: entry})
                if cmd in build_in_all_commands:
                    logging.warning(
                        f'"{entry}" plugin will overwrite the built-in "{cmd}" command.'
                    )
                logging.info(f'Registered command "{cmd}" by "{entry}" plugin.')

        self.commands_final_dict.update(plugin_class.plugin_commands_dict)
        plugins_dict[meta_name] = meta_info['description']
        return True

    @staticmethod
    def resolve_plugin_directory():
        """Return absolute plugin directory path, or ``None`` if missing.

        Returns:
            Absolute path to ``plugins`` or ``{data.path[:-1]}_plugins``, or
            ``None`` when the directory does not exist.
        """
        plugin_folder = "plugins"
        if data.path:
            plugin_folder = data.path[:-1] + '_plugins'
        abs_folder = os.path.abspath(plugin_folder)
        if not os.path.isdir(abs_folder):
            return None
        return abs_folder

    @staticmethod
    def get_all_prebuild_commands(built_in_commands_dict):
        """Expand built-in command names with aliases.

        Args:
            built_in_commands_dict: Built-in command name to ``Command`` map.

        Returns:
            Flat list of primary names and aliases.
        """
        result_list = []
        for command, command_data in built_in_commands_dict.items():
            result_list.append(command)
            if command_data.aliases:
                result_list.extend(command_data.aliases)
        return result_list

    @staticmethod
    def meta_is_valid(meta_info, entry):
        """Validate plugin ``meta_info`` against ``META_INFO_TEMPLATE``.

        Args:
            meta_info: Candidate meta dictionary from a plugin.
            entry: Plugin label used in error logs.

        Returns:
            True when meta is a complete, correctly typed dict.
        """
        if not isinstance(meta_info, dict):
            logging.error(f'Plugin "{entry}" metainfo is not a dictionary. '
                          'The plugin will not be loaded.')
            return False

        required_keys = set(META_INFO_TEMPLATE.keys())
        if not required_keys.issubset(meta_info.keys()):
            missing_keys = required_keys - set(meta_info.keys())
            missing_keys_text = ", ".join((f'"{i}"' for i in missing_keys))
            logging.error(f'Plugin "{entry}" metainfo is missing keys: {missing_keys_text}. '
                          'The plugin will not be loaded.')
            return False

        for key, expected_type in META_INFO_TEMPLATE.items():
            if not isinstance(meta_info.get(key), expected_type):
                logging.error(f'Plugin "{entry}" metainfo has incorrect type for key "{key}". '
                              f'Expected "{expected_type.__name__}", but got "{type(meta_info.get(key)).__name__}". '
                              f'The plugin will not be loaded.')
                return False
        return True

    @staticmethod
    def forbidden_dec_in_plug(file_path):
        """Return True when a plugin file uses forbidden handler decorators.

        Args:
            file_path: Absolute or relative path to a ``.py`` plugin source.

        Returns:
            True when a forbidden ``message_handler(commands=`` decorator is found.
        """
        with open(file_path, 'r', encoding='utf-8') as plugin:
            for line_num, line in enumerate(plugin, 1):
                lt, check_line = line.lstrip(), 'message_handler(commands='
                if lt.startswith(f'@bot.{check_line}') or lt.startswith(f'@utils.bot.{check_line}'):
                    logging.error(f'Forbidden decorator found in "{file_path}" on line {line_num}.')
                    logging.error(f'DO NOT USE "@(utils.)bot.message_handler(commands=" IN CODE! '
                                  f'USE plugin_commands_dict INSTEAD! The plugin will not be loaded.')
                    return True
        return False
