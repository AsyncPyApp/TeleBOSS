import logging
import os
import subprocess
import sys
import threading
import time
import traceback

from packaging import version
from packaging.requirements import Requirement
from importlib.metadata import version as importlib_version, PackageNotFoundError

import telebot

from teleboss.shared.parsers import html_fix
from teleboss.shared.runtime import data, bot, sqlWorker


def preflight_compatibility() -> str:
    """Validate local deps, SQL/config, and stored version before plugins.

    Performs only host-local checks (no Telegram, Git, threads, or version
    persistence). Rejects a stored version below ``data.MIN_VERSION``.

    Returns:
        The stored version string snapshot for later ``init``.
    """
    check_dependency_versions()
    data.sql_worker_get()

    stored_version = sqlWorker.params("version", default_return=data.VERSION)
    if version.parse(stored_version) < version.parse(data.MIN_VERSION):
        logging.error(
            f"You cannot upgrade from version {stored_version} because compatibility "
            f"is lost! Minimum version to upgrade to version {data.VERSION} - "
            f"{data.MIN_VERSION}"
        )
        sys.exit(1)
    return stored_version


def init(stored_version: str) -> None:
    """Finish host startup after plugins are constructed.

    Consumes the preflight version snapshot without re-deciding ``MIN_VERSION``
    rejection. Network identity, cleanup thread, changelog messaging, and
    version persistence remain here.

    Args:
        stored_version: Version string snapshot from ``preflight_compatibility``.
    """
    try:
        data.bot_id = bot.get_me().id
    except Exception as e:
        logging.error(f"Bot was unable to get own ID and will close - {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)

    threading.Thread(target=auto_clear, daemon=True).start()

    get_version = stored_version
    if version.parse(get_version) < version.parse(data.VERSION):
        change_type = "повышение"
        logging.warning(f"Version {get_version} upgraded to version {data.VERSION}")
    elif version.parse(get_version) > version.parse(data.VERSION):
        logging.warning("Version downgrade detected! This can lead to unpredictable consequences for the bot!")
        logging.warning(f"Downgraded from {get_version} to {data.VERSION}")
        change_type = "понижение"
    else:
        change_type = ""

    try:
        info = html_fix(get_last_commit_info().split('\n', maxsplit=1)[1])
        if len(info) > 2000:
            info = (info[:2000].rsplit(' ', 1)[0] +
                    '\n<i>чейнджлог коммита слишком длинный для вывода в сообщении...</i>')
        info = f'Информация о последних изменениях:\n<blockquote>{info}</blockquote>'
    except (FileNotFoundError, RuntimeError, IndexError) as e:
        if str(e) == "Folder .git not found":
            logging.warning('The .git folder was not found in the bot directory.')
        elif str(e) == "Command 'git' not found":
            logging.warning('The "git" command was not found. Please install Git to view commit history.')
        info = ('Информация о последних изменениях недоступна.\n'
                'Подробная информация о причинах ошибки содержится в логах бота.')

    update_text = "" if version.parse(get_version) == version.parse(data.VERSION) \
        else f"\nВнимание! Обнаружено {change_type} версии.\n" \
             f"Текущая версия: {data.VERSION}\n" \
             f"Предыдущая версия: {get_version}\n{info}"

    sqlWorker.params("version", rewrite_value=data.VERSION)
    logging.info(f'###TELEBOSS {data.VERSION} "{data.CODENAME.upper()}" '
                 f'BUILD DATE {data.BUILD_DATE} LAUNCHED SUCCESSFULLY!###')

    if data.main_chat_id == -1:
        logging.warning("WARNING! BOT LAUNCHED IN INIT MODE!\n***\n"
                        "You need to add TeleBOSS to your chat and use the /getchat command.\n"
                        "The bot will automatically write information about the ID of this chat\n"
                        "(and topic, if necessary) to the configuration file.\n"
                        "Restart the bot and work with it as usual.\n***")
        return

    try:
        if data.debug:
            logging.warning("BOT LAUNCHED IN DEBUG MODE!\n***\n"
                            "The bot will ignore the configuration of some parameters "
                            "and will not record changes to them.\n***")
            bot.send_message(data.main_chat_id, f"Бот запущен в режиме отладки!{update_text}",
                             message_thread_id=data.thread_id, parse_mode='html')
        else:
            bot.send_message(data.main_chat_id, f"Бот перезапущен.{update_text}",
                             message_thread_id=data.thread_id, parse_mode='html')
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Bot was unable to send a launch message and will be closed! "
                      f"Possibly the wrong value for the main chat or topic?\n{e}")
        sys.exit(1)


def check_dependency_versions() -> None:
    """Validate installed packages against ``requirements.txt`` and exit on failure."""
    file_name = 'requirements.txt'

    if not os.path.isfile(file_name):
        logging.warning(f'File "{file_name}" not found. The bot\'s library version check will not be performed.')
        return

    with open('requirements.txt', 'r') as f:

        for line in f:
            if not line.strip() or line.strip().startswith('#'):
                continue

            try:
                req = Requirement(line.strip())
            except Exception:
                logging.warning(f'Unable to parse requirement line "{line.strip()}", it will be skipped.')
                continue

            try:
                installed_ver = importlib_version(req.name)
            except PackageNotFoundError:
                logging.error(f"{req.name}: package is not installed\n"
                              "Please install the bot's dependencies before starting work. The bot will close.")
                sys.exit(1)

            if not req.specifier.contains(installed_ver, prereleases=True):
                logging.error(f"{req.name}: installed {installed_ver}, but {req.specifier} is required\n"
                              "Please update the bot's dependencies before starting work. The bot will close.")
                sys.exit(1)


def get_last_commit_info(count_of_commits=1, commit_index=0):
    """Return formatted git log text for recent commits.

    Args:
        count_of_commits: How many commits to include in the log.
        commit_index: How many newest commits to skip before reading.

    Returns:
        Formatted commit metadata and body text.

    Raises:
        FileNotFoundError: When the ``.git`` directory is missing.
        RuntimeError: When the ``git`` binary is missing or fails.
        IndexError: When ``commit_index`` exceeds the available history.
    """
    if not os.path.isdir('.git'):
        raise FileNotFoundError("Folder .git not found")

    try:
        commits_numbers = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'],
                                                  stderr=subprocess.STDOUT, encoding='utf-8').strip()
        if commit_index >= int(commits_numbers):
            raise IndexError(f'Commit index exceeds total count ({commits_numbers})')
        cmd = ['git', 'log', f'-{count_of_commits}', f'--skip={commit_index}',
               '--pretty=format:%ad by %an%n%B_2_strip', '--date=local']
        return (subprocess.check_output(cmd, stderr=subprocess.STDOUT, encoding='utf-8').
                strip().replace('\n_2_strip\n', '\n\n').replace('_2_strip', '\n'))
    except FileNotFoundError:
        raise RuntimeError("Command 'git' not found")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error while running 'git' command: {e}")
        logging.error(traceback.format_exc())
        raise RuntimeError(f"Error while running 'git' command: {e}")


def auto_clear():
    """Daemon loop that removes completed polls whose timer expired over ten minutes ago.

    Incomplete lifecycle states (``open``, ``completing``, ``failed``) are never
    deleted here. Only durable ``completed`` rows may be removed via
    :meth:`~teleboss.shared.storage.sql_worker.SqlWorker.delete_completed`.
    """
    while True:
        records = sqlWorker.get_all_polls()
        now = int(time.time())
        for record in records:
            if record[10] != "completed":
                continue
            if record[5] + 600 < now:
                if sqlWorker.delete_completed(record[0]):
                    logging.info('Removed deprecated poll "%s"', record[0])
        time.sleep(3600)


def register_commands(plugins_command_list, built_in_command_list):
    """Register plugin then built-in message handlers on the shared bot.

    Args:
        plugins_command_list: Plugin command name to ``Command`` mapping.
        built_in_command_list: Built-in command name to ``Command`` mapping.
    """
    for command_list in (plugins_command_list, built_in_command_list):
        for command, command_data in command_list.items():
            commands_list = [command]
            if command_data.aliases:
                commands_list.extend(command_data.aliases)
            handler_dict = {
                'function': command_data.command_func,
                'filters': {'commands': commands_list}
            }
            bot.add_message_handler(handler_dict)
