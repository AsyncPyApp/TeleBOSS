import configparser
import logging
import traceback

from teleboss.shared.runtime import data, bot


def bot_name_checker(message, get_chat=False) -> bool:
    """Crutch to prevent the bot from responding to other bots commands"""

    if message.text is None:
        return True

    if (data.main_chat_id != -1) == get_chat:
        return False

    cmd_text = message.text.split()[0]

    cmd_list = cmd_text.split('@', maxsplit=1)
    return len(cmd_list) == 1 or bot.get_me().username == cmd_list[-1]


def allowed_list(locked=False):
    lines = []
    for name, value in data.admin_allowed.items():
        status = "✅" if value else ("🔒" if locked else "❌")
        lines.append(f"{data.admin_rus[name]} {status}")
    return "\n".join(lines)


def welcome_msg_get(username, message):
    try:
        file = open(data.path + "welcome.txt", 'r', encoding="utf-8")
        welcome_msg = file.read().format(username, message.chat.title)
        file.close()
    except FileNotFoundError:
        logging.warning("file \"welcome.txt\" isn't found. The standard welcome message will be used.")
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    except (IOError, IndexError, KeyError, ValueError):
        logging.error("file \"welcome.txt\" isn't readable. The standard welcome message will be used.")
        logging.error(traceback.format_exc())
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    if welcome_msg == "":
        logging.warning("file \"welcome.txt\" is empty. The standard welcome message will be used.")
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    return welcome_msg


def write_init_chat(message):
    config = configparser.ConfigParser()
    try:
        config.read(data.path + "config.ini")
        config.set("Chat", "chat-id", str(message.chat.id))
        if message.message_thread_id is not None:
            config.set("Chat", "thread-id", str(message.message_thread_id))
            thread_ = " и темы "
        else:
            thread_ = " "
            config.set("Chat", "thread-id", "none")
        with open(data.path + "config.ini", "w") as config_file:
            config.write(config_file)
        bot.reply_to(message, f"ID чата{thread_}сохранён. "
                              "Теперь требуется перезапустить бота для перехода в нормальный режим.")
    except Exception as e:
        logging.error(str(e) + "\n" + traceback.format_exc())
        bot.reply_to(message, "Ошибка обновления конфига! Информация сохранена в логи бота!")


def command_forbidden(message, not_in_private_dialog=False, text=None):
    if not_in_private_dialog and message.chat.id == message.from_user.id:
        text = text or "Данную команду невозможно запустить в личных сообщениях."
        bot.reply_to(message, text)
        return True
    elif not_in_private_dialog:
        return False
    elif message.chat.id != data.main_chat_id:
        text = text or "Данную команду можно запустить только в основном чате."
        bot.reply_to(message, text)
        return True
    return None
