import fnmatch
import importlib
import logging
import os
import sys
import traceback

from packaging import version

from utils import data, Command
from poll_engine import PoolEngine

META_INFO_TEMPLATE = {
    'name': str,
    'type': str,
    'version-min': str,
    'version-max': str
}

class Plugins:

    def __init__(self, built_in_commands_dict):

        plugin_names = []
        registered_cmd_by_plugins = {}
        build_in_all_commands = self.get_all_prebuild_commands(built_in_commands_dict)
        built_in_commands_clear_dict = {i: j.command_func for i,j in built_in_commands_dict.items()}
        self.commands_final_dict = {}
        plugin_folder = "plugins"
        if data.path:
            plugin_folder = data.path[:-1] + '_plugins'
        if not os.path.isdir(plugin_folder):
            return
        files_list = os.listdir(plugin_folder)
        pattern = "*.py"
        for entry in files_list:
            if fnmatch.fnmatch(entry, pattern):
                if os.path.isdir(f"{plugin_folder}/{entry}"):
                    continue
                plugin_name = entry.split(".")[0]
                try:
                    if self.forbidden_dec_in_plug(f'{plugin_folder}/{entry}'):
                        continue
                    plugin_class = importlib.import_module(
                        f'{plugin_folder}.{plugin_name}').Plugin(built_in_commands_clear_dict.copy())
                    # We can reference built-in functions in Teleboss using a copy of the list,
                    # but we do not allow breaking the original list.
                    if not hasattr(plugin_class, 'meta_info'):
                        logging.error(f'Plugin "{entry}" has no meta_info attribute. The plugin will not be loaded.')
                        continue
                    meta_info = plugin_class.meta_info
                    if not self.meta_is_valid(meta_info, entry):
                        continue
                    if any([version.parse(meta_info['version-min']) > version.parse(data.VERSION),
                            version.parse(meta_info['version-max']) < version.parse(data.VERSION)]):
                        logging.error(f'Plugin "{entry}" need bot version {meta_info["version-min"]} '
                                      f'- {meta_info["version-max"]}, current is {data.VERSION}. '
                                      f'The plugin will not be loaded.')
                        continue
                    if meta_info['type'] not in ('simple', 'vote'):
                        logging.error(f'Plugin "{entry}" have an incorrect type (must be "simple" or "vote"). '
                                      f'The plugin will not be loaded.')
                        continue
                    elif meta_info['type'] == 'vote':
                        PoolEngine.post_vote_list.update(plugin_class.vote_list)

                    if hasattr(plugin_class, 'built_in_remove_list'):
                        for rem_cmd in plugin_class.built_in_remove_list:
                            if built_in_commands_dict.pop(rem_cmd, None):
                                logging.warning(f'The "{entry}" plugin has disabled the built-in "{rem_cmd}" command.')
                            else:
                                logging.error(f'Plugin "{entry}" is trying to disable command "{rem_cmd}" '
                                              'which has already been disabled or does not exist.')

                    if not hasattr(plugin_class, 'plugin_commands_dict'):
                        continue
                    for command, command_data in plugin_class.plugin_commands_dict.items():
                        if not (isinstance(command, str) and isinstance(command_data, Command)):
                            logging.error(f'Incorrect values in the plugin "{entry}" command list '
                                          f'(key must be str, value must be a "Command" class). The bot will close.')
                            sys.exit(1)
                        current_plugin_commands = [command]
                        if command_data.aliases:
                            current_plugin_commands.extend(command_data.aliases)
                        for cmd in current_plugin_commands:
                            registered_plugin_name = registered_cmd_by_plugins.get(cmd)
                            if registered_plugin_name == entry:
                                logging.error(f'Error in plugin "{entry}" - duplicate registration of "{cmd}" command '
                                              f'detected. The bot will close.')
                                sys.exit(1)
                            elif registered_plugin_name:
                                logging.error(f'Conflicting commands in plugins - the command "{cmd}" has already '
                                              f'been registered by another plugin "{registered_plugin_name}". '
                                              f'The bot will close.')
                                sys.exit(1)
                            registered_cmd_by_plugins.update({cmd: entry})
                            if cmd in build_in_all_commands:
                                logging.warning(f'"{entry}" plugin will overwrite the built-in "{cmd}" command.')
                            logging.info(f'Registered command "{cmd}" by "{entry}" plugin.')

                    self.commands_final_dict.update(plugin_class.plugin_commands_dict)
                    plugin_names.append(meta_info['name'])
                except Exception as e:
                    logging.error(f'Module "{entry}" is invalid! The bot will close.')
                    logging.error(e)
                    logging.error(traceback.format_exc())
                    sys.exit(1)
        if plugin_names:
            logging.info("Loaded plugins: " + ", ".join(plugin_names))
            data.plugins = plugin_names

    @staticmethod
    def get_all_prebuild_commands(built_in_commands_dict):
        result_list = []
        for command, command_data in built_in_commands_dict.items():
            result_list.append(command)
            if command_data.aliases:
                result_list.extend(command_data.aliases)
        return result_list

    @staticmethod
    def meta_is_valid(meta_info, entry):
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
        with open(file_path, 'r', encoding='utf-8') as plugin:
            for line_num, line in enumerate(plugin, 1):
                lt, check_line = line.lstrip(), 'message_handler(commands='
                if lt.startswith(f'@bot.{check_line}') or lt.startswith(f'@utils.bot.{check_line}'):
                    logging.error(f'Forbidden decorator found in "{file_path}" on line {line_num}.')
                    logging.error(f'DO NOT USE "@(utils.)bot.message_handler(commands=" IN CODE! '
                                  f'USE plugin_commands_dict INSTEAD! The plugin will not be loaded.')
                    return True
        return False
