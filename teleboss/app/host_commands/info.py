"""Info and diagnostics host command handlers."""

import logging
import time
import traceback

from teleboss.shared.access import bot_name_checker, command_forbidden, write_init_chat
from teleboss.shared.bootstrap import get_last_commit_info
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    reply_msg_target,
    topic_reply_fix,
)
from teleboss.shared.runtime import bot, data, helper, sqlWorker


class InfoMixin:
    """Mixin providing informational host commands."""

    @staticmethod
    def status(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        target_msg = message
        if topic_reply_fix(message.reply_to_message) is not None:
            target_msg = message.reply_to_message

        statuses = {"left": "покинул группу",
                    "kicked": "заблокирован",
                    "restricted": "ограничен",
                    "creator": "автор чата",
                    "administrator": "администратор",
                    "member": "участник"}

        user_id, username, is_bot = reply_msg_target(target_msg)
        user_status = bot.get_chat_member(data.main_chat_id, user_id).status

        if user_id == data.ANONYMOUS_ID:
            bot.reply_to(message, "Данный пользователь является анонимным администратором. "
                                  "Я не могу получить о нём информацию!")
            return

        not_bot_info = ""
        if not is_bot:
            if data.binary_chat_mode != 0:
                whitelist_status = "вайтлист отключён"
            elif sqlWorker.whitelist(target_msg.from_user.id):
                whitelist_status = "да"
            else:
                whitelist_status = "нет"
            mailing_status = "подписан" if sqlWorker.mailing(target_msg.from_user.id) else "не подписан"
            not_bot_info = f"\nНаличие в вайтлисте: {whitelist_status}" \
                           f"\nПодписка на рассылку: {mailing_status}"

        until_date = ""
        if user_status in ("kicked", "restricted"):
            if bot.get_chat_member(data.main_chat_id, user_id).until_date == 0:
                until_date = "\nОсталось до снятия ограничений: ограничен бессрочно"
            else:
                until_date = "\nОсталось до снятия ограничений: " + \
                             str(formatted_timer(bot.get_chat_member(data.main_chat_id, user_id)
                                                       .until_date - int(time.time())))

        abuse_text = ""
        abuse_chk = sum(sqlWorker.abuse_check(user_id))
        if abuse_chk > 0:
            abuse_text = ("\nТаймаут абуза инвайта для пользователя: "
                          f"{formatted_timer(abuse_chk - int(time.time()))}")

        restricted_status = ''
        if user_status == 'restricted':
            if bot.get_chat_member(data.main_chat_id, user_id).is_member:
                restricted_status = ', участник чата'
            else:
                restricted_status = ', не находится в чате'

        bot.reply_to(message, f"<b>Пользователь {html_fix(username)}:</b>\n"
                              f"Статус: {statuses.get(user_status)}{restricted_status}\n"
                              f"ID пользователя: <code>{user_id}</code>"
                              f"{until_date}{abuse_text}{not_bot_info}", parse_mode='html')


    @staticmethod
    def get_id(message):
        if extract_arg(message.text, 1) == "print" and data.debug:
            bot.reply_to(message, f"ID чата {message.chat.id}.\nID темы {message.message_thread_id}")
            return

        if not bot_name_checker(message, get_chat=True):
            return

        if message.chat.id == message.from_user.id:
            bot.reply_to(message, "Данная команда не может быть запущена в личных сообщениях.")
            return

        write_init_chat(message)


    @staticmethod
    def help_msg(message):
        if not bot_name_checker(message):
            return

        if message.from_user.id == message.chat.id:
            if bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("left", "kicked"):
                bot.reply_to(message, "У вас нет прав для использования этой команды.")
                return
        elif command_forbidden(message):
            return

        extended_help = ("\n<b>Форматирование времени (не зависит от регистра):</b>\n"
                        "<blockquote expandable>без аргумента или s - секунды\n"
                        "m - минуты\n"
                        "h - часы\n"
                        "d - дни\n"
                        "w - недели\n"
                        "Примеры использования: /abuse 12h30s, /timer 3600, /kickuser 30m12d12d</blockquote>\n\n"
                        "<b>Ключи --private и --public позволяют перезаписать настройки приватности для создаваемого "
                        "голосования (подробнее см. /votes help)</b>")

        try:
            help_main_text, help_main_keyboard = helper.get_main_list()
            bot.reply_to(message, help_main_text + extended_help, reply_markup=help_main_keyboard, parse_mode='html')
        except Exception as e:
            logging.error(f"{e}\n{traceback.format_exc()}")
            bot.reply_to(message, "Ошибка получения информации из JSON-файла помощи по командам! "
                                  "Информация об ошибке сохранена в логи бота.")


    @staticmethod
    def start(message):

        cmd_text = message.text.split()[0]
        if not cmd_text.endswith(f"@{bot.get_me().username}") and "@" in cmd_text:
            return

        if data.main_chat_id == -1:
            if message.chat.id != message.from_user.id:  # Проверка на init mode
                bot.reply_to(message, "В init режиме функции бота не работают. "
                                      "Используйте команду /getchat, которая автоматически сохранит информацию о "
                                      "данном чате и топике в файл конфигурации бота. Перезапустите бота. "
                                      "После этого его настройка будет завершена.")
            else:
                bot.reply_to(message, "В init режиме функции бота в личных сообщениях не работают.")
        elif message.chat.id == data.main_chat_id:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        elif message.chat.id == message.from_user.id:
            user_status = bot.get_chat_member(data.main_chat_id, message.from_user.id).status
            if user_status == "left":
                bot.reply_to(message, "Бот работает. Вы можете продолжить, если уверены в своих действиях.")
            elif user_status == "kicked":
                bot.reply_to(message, "Сейчас вы заблокированы в администрируемом мной чате. "
                                      "Вы можете продолжить, если уверены в своих действиях.")
            elif user_status == "restricted":
                bot.reply_to(message, "Сейчас вы имеете ограничения в администрируемом мной чате. "
                                      "Вы можете продолжить, если уверены в своих действиях.")
            elif user_status == "creator":
                bot.reply_to(message, "Владыка, давайте без формальностей, пожалуйста.")
            else:
                bot.reply_to(message, "Вам больше ничего не нужно делать, вы уже в чате.")
        else:
            is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
            if not is_allies:
                bot.reply_to(message, "Возможности данного бота ограничены вне основного и союзных чатов. "
                                      "Доступны команды /poll, /random и некоторые другие.")
            else:
                bot.reply_to(message, f"Благодарим за установление союзных отношений "
                                      f"с нашим чатом {bot.get_chat(data.main_chat_id).title}!")


    @staticmethod
    def overview(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        get_chat = bot.get_chat(data.main_chat_id)

        thread_text = ''
        if message.chat.is_forum:
            thread_id = message.message_thread_id if message.message_thread_id else 1
            thread_text = f"\n<b>ID топика:</b> <code>{thread_id}</code>"
        chat_description = (f"\n<b>Описание чата:</b>\n<blockquote expandable>"
                            f"{html_fix(get_chat.description)}</blockquote>") if get_chat.description else ""

        abuse_random_time = sqlWorker.abuse_random(data.main_chat_id)
        if abuse_random_time == -1:
            timer_random_text = "Команда /random отключена"
        elif abuse_random_time == 0:
            timer_random_text = "Кулдаун команды /random отключён"
        else:
            timer_random_text = f"{formatted_timer(abuse_random_time)} - кулдаун команды /random."

        auto_thresholds_mode = "" if not data.is_thresholds_auto() else " (авто)"
        auto_thresholds_ban_mode = "" if not data.is_thresholds_auto(True) else " (авто)"
        auto_thresholds_min_mode = "" if not data.is_thresholds_auto(minimum=True) else " (авто)"

        if data.binary_chat_mode == 0:
            chat_mode = "приватный"
        elif data.binary_chat_mode == 1:
            chat_mode = "публичный (с голосованием)"
        else:
            chat_mode = "публичный (с капчёй)"

        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            shield_info = f"включена, до отключения осталось {formatted_timer(shield_timer - int(time.time()))}"
        else:
            shield_info = "отключена"

        marmalade_text = "включена" if sqlWorker.params("marmalade", default_return=True) else "отключена"

        votes_list_len = len([record for record in sqlWorker.get_all_polls() if record[3] == data.main_chat_id])

        plugin_list = "Нет загруженных плагинов"
        if data.plugins:
            plugin_list = ("Список загруженных плагинов: " + ", ".join(data.plugins)
                           + "\n(для просмотра описания плагинов используйте /plugins)")

        reply_text = (
            f"<b>Версия Teleboss {data.VERSION} {data.CODENAME}, дата сборки: {data.BUILD_DATE}\n{plugin_list}\n\n</b>"
            f"<b>Название чата:</b> {html_fix(get_chat.title)}\n"
            f"<b>ID чата:</b> <code>{data.main_chat_id}</code>{thread_text}{chat_description}\n"
            f"<b>Количество участников</b>: {bot.get_chat_member_count(data.main_chat_id)}\n"
            f"<b>Количество союзных чатов</b>: {len(sqlWorker.get_allies())}\n"
            f"<code>&gt; чтобы получить полный список, см. /allies</code>\n"
            f"<b>Количество активных голосований:</b> {votes_list_len}\n"
            f"<code>&gt; чтобы получить полный список, см. /votes</code>\n\n"
            f"<b>Настройки защиты</b>\n"
            f"Режим приватности чата: {chat_mode}\n"
            f"<code>&gt; чтобы узнать подробнее, см. /private</code>\n"
            f"Состояние защиты Shield: {shield_info}\n"
            f"<code>&gt; чтобы узнать подробнее, см. /shield</code>\n"
            f"Состояние защиты Marmalade: {marmalade_text}\n"
            f"<code>&gt; чтобы узнать подробнее, см. /marmalade</code>\n\n"
            f"<b>Таймеры голосований</b>\n"
            f"Длительность обычных голосований: {formatted_timer(data.global_timer)}\n"
            f"Длительность бан-голосований: {formatted_timer(data.global_timer_ban)}\n"
            f"{timer_random_text}\n"
            f"<code>&gt; чтобы узнать подробнее, см. /timer help</code>\n\n"
            f"<b>Пороги количества голосов</b>\n"
            "Голосов для досрочного закрытия обычного голосования требуется (за любой вариант): "
            f"{data.thresholds_get()}{auto_thresholds_mode}\n"
            "Голосов для досрочного закрытия бан-голосования требуется (за любой вариант): "
            f"{data.thresholds_get(ban=True)}{auto_thresholds_ban_mode}\n"
            "Минимальный порог голосов, требуемых для принятия решения: "
            f"{data.thresholds_get(minimum=True)}{auto_thresholds_min_mode}\n"
            f"<code>&gt; чтобы узнать подробнее, см. /threshold help</code>\n\n"
            f"<b>Подробную справку о том, как работать с ботом, можно получить командой</b> <code>/help</code>"
        )

        bot.reply_to(message, reply_text, parse_mode='html')


    @staticmethod
    def version(message):
        if not bot_name_checker(message):
            return

        bot.reply_to(message, f'TeleBOSS, версия {data.VERSION} "{data.CODENAME}"\nДата сборки: {data.BUILD_DATE}\n'
                              f"Создан Allnorm aka DvadCat\n"
                              f"Самостоятельная линия развития (AsyncPyApp)")


    @staticmethod
    def plugins(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        plugin_list = "Никакие плагины сейчас не загружены."
        if data.plugins:
            plugin_list = (
                    "Список загруженных плагинов:\n" + "\n".join([f'{num}. {name}\nОписание: {data.plugins[name]}'
                                                                  for num, name in enumerate(data.plugins, start=1)]))
        bot.reply_to(message, plugin_list)


    @staticmethod
    def git(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        try:
            count = int(extract_arg(message.text, 1))
        except ValueError:
            bot.reply_to(message, "Аргумент количества выводимых коммитов не является числом!")
            return
        except TypeError:
            count = 1

        try:
            index = int(extract_arg(message.text, 2))
        except ValueError:
            bot.reply_to(message, "Аргумент порядкового номера коммита не является числом!")
            return
        except TypeError:
            index = 1

        if count <= 0:
            bot.reply_to(message, "Количество коммитов для вывода не может быть меньше или равно нулю.")
            return

        if index <= 0:
            bot.reply_to(message, "Порядковый номер коммита не может быть меньше или равен нулю")
            return

        try:
            info = html_fix(get_last_commit_info(count_of_commits=count, commit_index=index - 1))
            if len(info) > 3800:
                info = (info[:3800].rsplit(' ', 1)[0] +
                        '\n<i>чейнджлог коммитов слишком длинный для вывода в сообщении...</i>')
            info = f'Информация о последних изменениях:\n<blockquote expandable>{info}</blockquote>'
        except (FileNotFoundError, RuntimeError, IndexError) as e:
            if str(e) == "Folder .git not found":
                info = "Папка .git не найдена в рабочем каталоге бота.\nИстория изменений недоступна."
            elif str(e) == "Command 'git' not found":
                info = 'Команда "git" не найдена.\nОбратитесь к хостеру бота для установки Git на хостинг.'
            elif 'Commit index exceeds total count' in str(e):
                commits_total_count = str(e).rsplit(" ", maxsplit=1)[1]
                info = f'Порядковый номер коммита превысил общее количество коммитов {commits_total_count}'
            else:
                info = ('Ошибка выполнения команды git.\nПодробная информация '
                        'о причинах ошибки содержится в логах бота.')

        bot.reply_to(message, info, parse_mode='html')
