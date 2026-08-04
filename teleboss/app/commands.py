import json
import logging
import multiprocessing
import os
import queue
import random
import time
import traceback

import telebot

from teleboss.domain.admin.prevote import (
    Avatar,
    Deop,
    Description,
    OpSetup,
    Rank,
    RemoveTopic,
    Title,
)
from teleboss.domain.allies.prevote import AlliesList
from teleboss.domain.content.prevote import CustomPoll, Rules
from teleboss.domain.moderation.prevote import (
    Ban,
    Invite,
    Kick,
    MessageRemover,
    MessageSilentRemover,
    Mute,
    Unban,
)
from teleboss.domain.settings.prevote import (
    Marmalade,
    PrivateMode,
    Rating,
    Shield,
    Thresholds,
    Timer,
    Votes,
    Whitelist,
)
from teleboss.shared.access import bot_name_checker, command_forbidden, write_init_chat
from teleboss.shared.bootstrap import get_last_commit_info
from teleboss.shared.calc import calc_engine
from teleboss.shared.command import Command
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    reply_msg_target,
    time_parser,
    topic_reply_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data, helper, sqlWorker
from teleboss.voting.engine import poll_engine


class BuildInCommands:

    def __init__(self):
        self.built_in_commands_dict = {
            'invite': Command(self.add_usr, None),
            'ban': Command(self.ban_usr, ('banuser',)),
            'kick': Command(self.kick_usr, ('kickuser',)),
            'mute': Command(self.mute_usr, None),
            'unmute': Command(self.unban_usr, ('unban',)),
            'threshold': Command(self.thresholds, None),
            'timer': Command(self.timer, None),
            'rate': Command(self.rate, None),
            'whitelist': Command(self.whitelist, None),
            'delete': Command(self.delete_msg, None),
            'clear': Command(self.clear_msg, None),
            'private': Command(self.private_mode, None),
            'op': Command(self.op, None),
            'remtopic': Command(self.rem_topic, None),
            'rank': Command(self.rank, None),
            'deop': Command(self.deop, None),
            'title': Command(self.title, None),
            'description': Command(self.description, None),
            'chatpic': Command(self.chat_pic, None),
            'allies': Command(self.allies_list, None),
            'shield': Command(self.shield, None),
            'rules': Command(self.rules_msg, None),
            'poll': Command(self.custom_poll, None),
            'votes': Command(self.votes, None),
            'marmalade': Command(self.marmalade, None),
            'answer': Command(self.add_answer, None),
            'mail': Command(self.mail, None),
            'status': Command(self.status, None),
            'random': Command(self.random_msg, ('redrum',)),
            'pardon': Command(self.pardon, None),
            'getchat': Command(self.get_id, None),
            'help': Command(self.help_msg, None),
            'kill': Command(self.mute_user, None),
            'revoke': Command(self.revoke, None),
            'cremate': Command(self.cremate, None),
            'calc': Command(self.calc, None),
            'start': Command(self.start, None),
            'overview': Command(self.overview, None),
            'version': Command(self.version, None),
            'plugins': Command(self.plugins, None),
            'git': Command(self.git, None),
            'niko': Command(self.niko, None),
        }

    @staticmethod
    def add_usr(message):
        Invite(message)


    @staticmethod
    def ban_usr(message):
        Ban(message)


    @staticmethod
    def kick_usr(message):
        Kick(message)


    @staticmethod
    def mute_usr(message):
        Mute(message)


    @staticmethod
    def unban_usr(message):
        Unban(message)


    @staticmethod
    def thresholds(message):
        Thresholds(message)


    @staticmethod
    def timer(message):
        Timer(message)


    @staticmethod
    def rate(message):
        Rating(message)


    @staticmethod
    def whitelist(message):
        Whitelist(message)


    @staticmethod
    def delete_msg(message):
        MessageRemover(message)


    @staticmethod
    def clear_msg(message):
        MessageSilentRemover(message)


    @staticmethod
    def private_mode(message):
        PrivateMode(message)


    @staticmethod
    def op(message):
        OpSetup(message)


    @staticmethod
    def rem_topic(message):
        RemoveTopic(message)


    @staticmethod
    def rank(message):
        Rank(message)


    @staticmethod
    def deop(message):
        Deop(message)


    @staticmethod
    def title(message):
        Title(message)


    @staticmethod
    def description(message):
        Description(message)


    @staticmethod
    def chat_pic(message):
        Avatar(message)


    @staticmethod
    def allies_list(message):
        AlliesList(message)


    @staticmethod
    def shield(message):
        Shield(message)


    @staticmethod
    def rules_msg(message):
        Rules(message)


    @staticmethod
    def custom_poll(message):
        CustomPoll(message)


    @staticmethod
    def votes(message):
        Votes(message)


    @staticmethod
    def marmalade(message):
        Marmalade(message)


    @staticmethod
    def add_answer(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if topic_reply_fix(message.reply_to_message) is None:
            bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на заявку на вступление")
            return

        poll = sqlWorker.get_poll(message.reply_to_message.id)
        if poll:
            if poll[0][2] != "invite":
                bot.reply_to(message, "Данное голосование не является голосованием о вступлении.")
                return
        else:
            bot.reply_to(message, "Заявка на вступление не найдена или закрыта.")
            return

        try:
            msg_from_usr = message.text.split(None, 1)[1]
        except IndexError:
            bot.reply_to(message, "Ответ не может быть пустым.")
            return

        data_list = json.loads(poll[0][6])

        try:
            bot.send_message(data_list[0], "Сообщение на вашу заявку от участника чата - \"" + msg_from_usr + "\"")
            bot.reply_to(message, "Сообщение пользователю отправлено успешно.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error sending message to applicant for membership!\n{e}')
            bot.reply_to(message, "Ошибка отправки сообщению пользователю.")


    @staticmethod
    def mail(message):
        if not bot_name_checker(message):
            return

        if message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(message, "Вы не можете подписаться на рассылку, так как являетесь анонимным администратором.")
            return

        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("kicked", "left"):
            bot.reply_to(message, "Вы не можете подписаться на рассылку, если не состоите в чате.")
            return

        if extract_arg(message.text, 1) == "status":
            subscribed = " " if sqlWorker.mailing(message.from_user.id) else " не "
            bot.reply_to(message, f"Вы{subscribed}подписаны на рассылку и{subscribed}получаете информацию о новых "
                                  f"голосованиях в чате.\n<b>Обратите внимание, что если боту будет запрещено писать "
                                  "вам в личные сообщения, рассылка отключится автоматически!\n"
                                  "Переключить статус рассылки можно командой /mail.</b>",
                         parse_mode='html')
            return

        if sqlWorker.mailing(message.from_user.id):
            sqlWorker.mailing(message.from_user.id, remove=True)
            subscribed = "отключили"
        else:
            sqlWorker.mailing(message.from_user.id, add=True)
            subscribed = "подключили"
        bot.reply_to(message, f"Вы {subscribed} рассылку о новых голосованиях в личных сообщениях бота.")


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
    def random_msg(message):
        if not bot_name_checker(message):
            return

        try:
            abuse_vote_timer = int(poll_engine.vote_abuse.get("random"))
        except TypeError:
            abuse_vote_timer = 0

        abuse_random = sqlWorker.abuse_random(message.chat.id)

        if abuse_vote_timer + abuse_random > int(time.time()) or abuse_random < 0:
            return

        poll_engine.vote_abuse.update({"random": int(time.time())})

        msg_id = ""
        for i in range(5):
            try:
                msg_id = random.randint(1, message.id)
                bot.forward_message(message.chat.id, message.chat.id, msg_id,
                                    message_thread_id=message.message_thread_id)
                return
            except telebot.apihelper.ApiTelegramException as e:
                if "message has protected content and can't be forwarded" in str(e):
                    bot.reply_to(message, "Пересылка рандомных сообщений невозможна, чат защищён от копирования.")
                    return
                elif i == 4:
                    logging.error(f'Error forwarding random message with number {msg_id} '
                                  f'in chat {message.chat.id}!\n{e}')
                    bot.reply_to(message, f"Ошибка взятия рандомного сообщения с номером {msg_id}!")


    @staticmethod
    def pardon(message):
        if not bot_name_checker(message):
            return

        if message.chat.id == data.main_chat_id:
            if bot.get_chat_member(data.main_chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "Данная команда не может быть запущена в основном чате не администраторами.")
            elif topic_reply_fix(message.reply_to_message) is None:
                bot.reply_to(message, "Требуется реплейнуть сообщение участника, "
                                      "которому вы хотите сбросить абуз инвайта.")
            elif message.reply_to_message.from_user.id == data.bot_id:
                bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            else:
                user_id, username, _ = reply_msg_target(message.reply_to_message)
                sqlWorker.abuse_remove(user_id)
                bot.reply_to(message, f"Абуз инвайта для {username} сброшен!")
                return
        elif data.debug:
            sqlWorker.abuse_remove(message.chat.id)
            target = "инвайт" if message.chat.id == message.from_user.id else "добавление в союзники"
            user = "пользователя" if message.chat.id == message.from_user.id else "чата"
            bot.reply_to(message, f"Абуз заявки на {target} сброшен для текущего {user}.")
            return
        else:
            bot.reply_to(message, "Данная команда не может быть запущена в обычном режиме вне основного чата.")


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
    def mute_user(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if data.kill_mode == 0:
            bot.reply_to(message, "Команда /kill отключена в файле конфигурации бота.")
            return

        if topic_reply_fix(message.reply_to_message) is None:

            if data.kill_mode == 2:
                only_for_admins = "\nВ текущем режиме команду могут применять только администраторы чата."
            else:
                only_for_admins = ""

            bot.reply_to(message, "Ответьте на сообщение пользователя, которого необходимо отправить в мут.\n"
                         + "ВНИМАНИЕ: использовать только в крайних случаях - во избежание злоупотреблений "
                         + "вы так же будете лишены прав на тот же срок.\n"
                         + "Даже если у вас есть права админа, вы будете их автоматически лишены, "
                         + "если они были выданы с помощью бота." + only_for_admins)
            return

        if data.bot_id == message.reply_to_message.from_user.id:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if data.ANONYMOUS_ID in [message.reply_to_message.from_user.id, message.from_user.id]:
            bot.reply_to(message, "Я не могу ограничить анонимного пользователя!")
            return

        if message.from_user.id != message.reply_to_message.from_user.id and data.kill_mode == 2:
            if bot.get_chat_member(data.main_chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "В текущем режиме команду могут применять только администраторы чата.")
                return

        if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
            bot.reply_to(message, "Он и так в муте, не увеличивайте его страдания.")
            return

        if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status in ("kicked", "left"):
            bot.reply_to(message, "Данный пользователь не состоит в чате.")
            return

        timer_mute = 3600
        if extract_arg(message.text, 1) is not None:
            timer_mute = time_parser(extract_arg(message.text, 1))
            if timer_mute is None:
                bot.reply_to(message, "Неправильный аргумент, укажите время мута от 31 секунды до 12 часов.")
                return

        if not 30 < timer_mute <= 43200:
            bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 12 часов.")
            return

        try:
            abuse_vote_timer = int(poll_engine.vote_abuse.get("abuse" + str(message.from_user.id)))
        except TypeError:
            abuse_vote_timer = 0

        if abuse_vote_timer + 10 > int(time.time()):
            return

        poll_engine.vote_abuse.update({"abuse" + str(message.from_user.id): int(time.time())})

        try:
            bot.restrict_chat_member(data.main_chat_id, message.reply_to_message.from_user.id,
                                     until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
            if message.from_user.id == message.reply_to_message.from_user.id:
                if data.rate:
                    sqlWorker.update_rate(message.from_user.id, -3)
                    bot.reply_to(message, f"Пользователь {username_parser(message)}"
                                 + f" решил отдохнуть от чата на {formatted_timer(timer_mute)}"
                                 + " и снизить себе рейтинг на 3 пункта.")
                else:
                    bot.reply_to(message, f"Пользователь {username_parser(message)}"
                                 + f" решил отдохнуть от чата на {formatted_timer(timer_mute)}")
                return
            if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                    and data.rate:
                sqlWorker.update_rate(message.reply_to_message.from_user.id, -5)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error restricting attacked user with /kill command!\n{e}')
            bot.reply_to(message, "Я не смог снять права данного пользователя. Не имею права.")
            return

        try:
            bot.restrict_chat_member(data.main_chat_id, message.from_user.id,
                                     until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
            if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                    and data.rate:
                sqlWorker.update_rate(message.from_user.id, -5)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error restricting initiator user with /kill command!\n{e}')
            bot.reply_to(message, "Я смог снять права данного пользователя на "
                         + formatted_timer(timer_mute) + ", но не смог снять права автора заявки.")
            return

        user_rate = ""
        if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                and data.rate:
            user_rate = "\nРейтинг обоих пользователей снижен на 5 пунктов."

        bot.reply_to(message, f"<b>Обоюдоострый Меч сработал</b>.\nТеперь {username_parser(message, True)} "
                              f"и {username_parser(message.reply_to_message, True)} "
                              f"будут дружно молчать в течении " + formatted_timer(timer_mute) + user_rate,
                     parse_mode="html")


    @staticmethod
    def revoke(message):
        if not bot_name_checker(message):
            return

        is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
        if not is_allies:
            if command_forbidden(message, text="Данную команду можно запустить только "
                                                     "в основном чате или в союзных чатах."):
                return

        try:
            bot.revoke_chat_invite_link(data.main_chat_id, bot.get_chat(data.main_chat_id).invite_link)
            bot.reply_to(message, "Пригласительная ссылка на основной чат успешно сброшена.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error resetting invitation link!\n{e}')
            bot.reply_to(message, "Ошибка сброса основной пригласительной ссылки! Подробная информация в логах бота.")


    @staticmethod
    def cremate(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if topic_reply_fix(message.reply_to_message):
            user_id = message.reply_to_message.from_user.id
        elif extract_arg(message.text, 1) is not None:
            try:
                user_id = int(extract_arg(message.text, 1))
            except ValueError:
                bot.reply_to(message, "Указан неверный User ID.")
                return
        else:
            bot.reply_to(message, "Требуется реплейнуть сообщение удалённого аккаунта "
                                  "или ввести ID аккаунта аргументом команды.")
            return

        if user_id == data.bot_id:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        try:
            first_name = bot.get_chat_member(data.main_chat_id, user_id).user.first_name
        except telebot.apihelper.ApiTelegramException as e:
            if "invalid user_id specified" in str(e):
                bot.reply_to(message, "Указан неверный User ID.")
            else:
                logging.error(f'Error getting account information when trying to cremate!\n{e}')
                bot.reply_to(message, "Неизвестная ошибка Telegram API. Информация сохранена в логи бота.")
            return

        if bot.get_chat_member(data.main_chat_id, user_id).status in ('left', 'kicked'):
            bot.reply_to(message, "Данный участник не находится в чате.")
        elif first_name == '':
            try:
                bot.ban_chat_member(data.main_chat_id, user_id, int(time.time()) + 60)
                bot.reply_to(message, "Удалённый аккаунт успешно кремирован.")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Account cremation error!\n{e}')
                bot.reply_to(message, "Ошибка кремации удалённого аккаунта. Недостаточно прав?")
        else:
            bot.reply_to(message, "Данный участник не является удалённым аккаунтом.")

    @staticmethod
    def calc(message):
        if not bot_name_checker(message):
            return

        is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
        user_status = bot.get_chat_member(data.main_chat_id, message.from_user.id).status
        if not (is_allies or user_status in ("creator", "administrator", "member")):
            if command_forbidden(message, text="Данную команду можно запустить только в основном чате, "
                                                     "участникам основного чата или в союзных чатах."):
                return

        if extract_arg(message.text, 1) is None:
            bot.reply_to(message, "Данная команда не может быть запущена без аргумента.")
            return

        calc_text = message.text.split(maxsplit=1)[1]
        if len(calc_text.replace(" ", "")) > 500:
            bot.reply_to(message, "В выражении должно быть не более 500 полезных символов.")
            return
        if not set(calc_text).issubset("1234567890 */+-().,^"):
            bot.reply_to(message, "Неверно введено выражение для вычисления.")
            return

        to_send = multiprocessing.Queue()
        process = multiprocessing.Process(target=calc_engine, args=(calc_text, to_send))
        process.start()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            bot.reply_to(message, "Время вычисления превысило таймаут. Отменено.")
            return

        try:
            calc_result = to_send.get(timeout=5)
        except queue.Empty:
            bot.reply_to(message, "Неизвестная ошибка вычисления! Информация сохранена в логи бота.")
            return

        try:
            bot.reply_to(message, calc_result, parse_mode='html')
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is too long' in str(e):
                bot.reply_to(message, "Результат слишком большой для отправки.")


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


    @staticmethod
    def niko(message):
        if not bot_name_checker(message):
            return

        try:
            bot.send_sticker(message.chat.id, random.choice(bot.get_sticker_set("OneShotSolstice").stickers).file_id,
                             message_thread_id=message.message_thread_id)
            # bot.send_sticker(message.chat.id, open(os.path.join("ee", random.choice(os.listdir("ee"))), 'rb'))
            # Random file
        except (FileNotFoundError, telebot.apihelper.ApiTelegramException, IndexError):
            pass
