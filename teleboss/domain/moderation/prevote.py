import logging
import random
import threading
import time
from typing import Optional

import telebot
from telebot import types

from teleboss.shared.access import bot_name_checker, command_forbidden, welcome_msg_get
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    reply_msg_target,
    time_parser,
    topic_reply_fix,
    username_parser,
    username_parser_invite,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote


class Invite(PreVote):

    def pre_return(self) -> Optional[bool]:
        if not bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in \
               ("left", "kicked", "restricted"):
            bot.reply_to(self.message, "Вы уже есть в нужном вам чате.")
            return True
        self.user_id = data.bot_id
        return None

    def arg_fn(self, _):
        self.direct_fn()

    def direct_fn(self):

        if data.binary_chat_mode != 0 or sqlWorker.whitelist(self.message.from_user.id):  # 0 - mode with whitelist
            if sqlWorker.params("shield", default_return=0) > int(time.time()) and data.binary_chat_mode != 0:
                bot.reply_to(self.message, "В режиме защиты инвайт-ссылка на чат не выдаётся!")
                return

            try:
                invite_link = bot.get_chat(data.main_chat_id).invite_link
                if invite_link is None:
                    bot.reply_to(self.message, "Ошибка получения ссылки на чат. Недостаточно прав?")
                    return
                until_date = ""
                abuse_chk = sum(sqlWorker.abuse_check(self.message.from_user.id))
                if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "kicked":
                    if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).until_date == 0:
                        until_date = "Внимание! Вы бессрочно заблокированы в данном чате!\n"
                    else:
                        until_timer = formatted_timer(bot.get_chat_member(data.main_chat_id,
                                                                                self.message.from_user.id).until_date
                                                            - int(time.time()))
                        until_date = "Внимание! Вы заблокированы в данном чате! " \
                                     f"До снятия ограничений осталось {until_timer}\n"
                elif abuse_chk > 0:
                    until_date = until_date + "Внимание! Вы находитесь под ограничением абуза инвайта! " \
                                              f"Вам следует подождать ещё " \
                                              f"{formatted_timer(abuse_chk - int(time.time()))}, " \
                                              f"в противном случае при попытке входа в чат вы будете заблокированы."
                bot.reply_to(self.message, f"Ссылка на администрируемый мной чат:\n{invite_link}\n{until_date}")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error when trying to issue a link to a new participant!\n{e}')
                bot.reply_to(self.message, "Ошибка получения ссылки на чат. Недостаточно прав?")
            return

        self.unique_id = str(self.message.from_user.id) + "_useradd"
        if self.is_voting_exist():
            return

        abuse_chk = sum(sqlWorker.abuse_check(self.message.from_user.id))
        if abuse_chk > 0:
            bot.reply_to(self.message, "Сработала защита от абуза инвайта! Вам следует подождать ещё "
                         + formatted_timer(abuse_chk - int(time.time())))
            return

        try:
            msg_from_usr = self.msg_txt.split(None, 1)[1]
        except IndexError:
            msg_from_usr = "нет"

        self.vote_text = ("Тема голосования: заявка на вступление от пользователя <a href=\"tg://user?id="
                          + str(self.message.from_user.id) + "\">"
                          + username_parser(self.message, True) + "</a>.\n"
                          + "Сообщение от пользователя: " + html_fix(msg_from_usr) + ".")
        self.vote_args = [self.message.chat.id, username_parser(self.message), self.message.from_user.id]
        self.poll_maker(add_user=True, vote_type="invite")

        warn = ""
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "kicked":
            warn = "\nВнимание! Вы были заблокированы в чате ранее, поэтому вероятность инвайта минимальная!"
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "restricted":
            warn = "\nВнимание! Сейчас на вас распространяются ограничения прав в чате, выданные командой /mute!"
        bot.reply_to(self.message, "Голосование о вступлении отправлено в чат. Голосование завершится через "
                     + formatted_timer(data.global_timer) + " или ранее." + warn)


class Ban(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которого требуется забанить.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу заблокировать анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True
        return None

    def arg_fn(self, arg):
        restrict_timer = time_parser(extract_arg(self.msg_txt, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if extract_arg(self.msg_txt, 2) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=2)[2]
        self.ban(restrict_timer, True, f"\nПредложенный срок блокировки: {formatted_timer(restrict_timer)}", 1)

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.ban(0, False, "\nПредложенный срок блокировки: <b>перманентный</b>", 2)

    def ban(self, restrict_timer, kick_user, ban_timer_text, vote_type):

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "left" and kick_user:
            bot.reply_to(self.message, "Пользователя нет в чате, чтобы можно было кикнуть его.")
            return

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "блокировка пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            vote_theme = "изменение срока блокировки пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = f"Тема голосования: {vote_theme} {html_fix(self.reply_username)}" + \
                         date_unban + html_fix(self.ban_reason) + ban_timer_text + \
                         f"\nИнициатор голосования: {username_parser(self.message, True)}."

        self.vote_args = [self.reply_user_id, self.reply_username, username_parser(self.message),
                          vote_type, restrict_timer, self.ban_reason]

        self.poll_maker()


class Kick(Ban):

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.ban(3600, True, f"\nПредложенный срок блокировки: {formatted_timer(3600)}", 1)


class Mute(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> Optional[bool]:

        if not bot_name_checker(self.message) or command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется замутить.")
            return True

        self.reply_msg_target()
        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу ограничить анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            bot.reply_to(self.message, "Данный пользователь уже забанен или кикнут.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True
        return None

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.mute(0, "\nПредложенный срок ограничений: перманентно")

    def arg_fn(self, arg):
        restrict_timer = time_parser(extract_arg(self.msg_txt, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if extract_arg(self.msg_txt, 2) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=2)[2]
        self.mute(restrict_timer, f"\nПредложенный срок ограничений: {formatted_timer(restrict_timer)}")

    def mute(self, restrict_timer, ban_timer_text):

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "ограничение сообщений пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            vote_theme = "изменение срока ограничения сообщений пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = (f"Тема голосования: {vote_theme} {html_fix(self.reply_username)}" +
                          date_unban + html_fix(self.ban_reason) + ban_timer_text +
                          f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username,
                          username_parser(self.message), 0, restrict_timer, self.ban_reason]
        self.poll_maker()


class Unban(PreVote):
    vote_type = "unban"

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется "
                                       "размутить, разбанить или обнулить значение абуза инвайта.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу разблокировать анонимного администратора!")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status not in ("restricted", "kicked") and \
                sum(sqlWorker.abuse_check(self.reply_user_id)) == 0:
            bot.reply_to(self.message, "Данный пользователь не ограничен.")
            return True
        return None

    def direct_fn(self):
        self.unique_id = str(self.reply_user_id) + "_unban"
        if self.is_voting_exist():
            return

        self.vote_text = ("Тема голосования: снятие ограничений с пользователя "
                          + html_fix(self.reply_username) +
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username, username_parser(self.message)]
        self.poll_maker()


class MessageRemover(PreVote):
    warn = ""
    clear = ""
    vote_type = "delete message"

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которое требуется удалить.")
            return True

        self.reply_user_id, self.reply_username, self.reply_is_bot \
            = reply_msg_target(self.message.reply_to_message)

        if data.bot_id == self.reply_user_id and sqlWorker.get_poll(self.message.reply_to_message.id):
            bot.reply_to(self.message, "Вы не можете удалить голосование до его завершения!")
            return True

        if all([data.bot_id != self.reply_user_id, self.reply_is_bot, self.reply_user_id != data.ANONYMOUS_ID]):
            bot.reply_to(self.message, f"Боты в Telegram не могут удалять сообщения других ботов!")
            return True
        return None

    def direct_fn(self):
        self.unique_id = str(self.message.reply_to_message.message_id) + "_delmsg"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: удаление сообщения пользователя {html_fix(self.reply_username)}"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}." + self.warn)
        self.vote_args = [self.message.reply_to_message.message_id, self.reply_username, self.silent]
        self.poll_maker(silent=self.silent)


class MessageSilentRemover(MessageRemover):
    warn = "\n\n<b>Внимание, голосования для бесследной очистки не закрепляются автоматически. Пожалуйста, " \
           "закрепите их самостоятельно при необходимости.</b>\n"
    silent = True
    clear = "бесследно "

    @staticmethod
    def timer_votes_init():
        return data.global_timer, data.thresholds_get()


class NewUserChecker(PreVote):
    vote_type = "captcha"
    abuse_time = [0, 0]

    def pre_return(self) -> bool:
        if data.main_chat_id == -1:  # Проверка на init mode
            return True

        self.reply_username = username_parser_invite(self.message)
        self.reply_user_id = self.message.json.get("new_chat_participant").get("id")
        self.reply_is_bot = self.message.json.get("new_chat_participant").get("is_bot")
        self.user_id = data.bot_id

        if data.main_chat_id != self.message.chat.id:  # В чужих чатах не следим
            self.marmalade_ally() # Но союзный чат - не чужой чат)))
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Приветствую вас, Владыка.")
            return True

        if sqlWorker.params("shield", default_return=0) > int(time.time()):
            if sqlWorker.whitelist(self.reply_user_id) and data.binary_chat_mode == 0:
                sqlWorker.abuse_update(self.message.from_user.id, timer=3600, force=True)
                bot.reply_to(self.message, "Данный участник есть в вайтлисте и не будет заблокирован в режиме защиты!")
            else:
                try:
                    bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=int(time.time() + 3600))
                    bot.delete_message(self.message.chat.id, self.message.id)
                    bot.delete_message(self.message.chat.id, self.message.id + 1)
                except telebot.apihelper.ApiTelegramException:
                    pass
            return True

        self.abuse_time = sqlWorker.abuse_check(self.reply_user_id, True)
        if sum(self.abuse_time) > int(time.time()):
            try:
                bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=sum(self.abuse_time))
                bot.reply_to(self.message,
                             "\u26a0\ufe0f <b>НЕ ХЛОПАТЬ ДВЕРЬЮ!</b> \u26a0\ufe0f\nСработала защита от абуза инвайта! "
                             "Повторная попытка возможна через "
                             f"{formatted_timer(sum(self.abuse_time) - int(time.time()))}", parse_mode="html")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error blocking a new participant!\n{e}')
                bot.reply_to(self.message, "Ошибка блокировки вошедшего в режиме защиты пользователя!"
                                           "Информация сохранена в логах бота!")
            return True

        if self.reply_is_bot:
            if self.reply_user_id != data.bot_id:
                self.for_bots()
            return True
        if self.allies_whitelist_add():
            return True
        if data.binary_chat_mode == 0:
            self.whitelist_mode()
        elif data.binary_chat_mode == 1:
            self.vote_mode()
        else:
            self.captcha_mode()
        return True  # direct_fn() не выполняется

    def marmalade_ally(self):
        if not sqlWorker.params("marmalade", default_return=True):
            return
        allies = sqlWorker.get_allies()
        is_ally = False
        for ally_id in allies:
            if ally_id[0] == self.message.chat.id:
                is_ally = True
        if not is_ally or bot.get_chat_member(data.main_chat_id, self.reply_user_id).status not in ('left', 'kicked'):
            return
        entry_time = sqlWorker.marmalade_get(self.reply_user_id)
        if not entry_time or entry_time + data.marmalade_reset_timer < int(time.time()):
            if data.binary_chat_mode != 0 or not sqlWorker.whitelist(self.message.from_user.id):
                sqlWorker.marmalade_add(self.reply_user_id, int(time.time()))

    def is_voting_exist(self):
        message_id = sqlWorker.get_message_id(self.unique_id)
        if message_id:
            poll = sqlWorker.get_poll(message_id)
            if poll[0][5] <= int(time.time()):
                sqlWorker.rem_rec(poll[0][0])
                return False
            else:
                bot.reply_to(self.message, "Голосование о добавлении участника уже существует.")
                return True
        return False

    def for_bots(self):
        self.unique_id = str(self.reply_user_id) + "_new_usr"
        if self.is_voting_exist():
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False,
                                     until_date=int(time.time()) + 900)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new bot!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового бота. Недостаточно прав?")
            return

        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 300
        self.vote_text = ("Требуется подтверждение вступления нового бота, добавленного пользователем " +
                          username_parser(self.message, True) +
                          f", в противном случае он будет кикнут на {formatted_timer(until_time)}")
        self.poll_maker(current_timer=900, vote_args=[self.reply_username, self.reply_user_id, "бота", until_time])

    def allies_whitelist_add(self):
        allies = sqlWorker.get_allies()
        if not allies:
            return None
        for ally_id in allies:
            try:
                usr_status = bot.get_chat_member(ally_id[0], self.reply_user_id).status
                if usr_status not in ["left", "kicked"]:
                    if sqlWorker.params("marmalade", default_return=True):
                        entry_time = sqlWorker.marmalade_get(self.reply_user_id)
                        if entry_time and entry_time + data.marmalade_timer > int(time.time()):
                            if data.binary_chat_mode == 0 and not sqlWorker.whitelist(self.reply_user_id):
                                self.vote_mode()
                                return True
                            else:
                                return False
                        else:
                            sqlWorker.marmalade_remove(self.reply_user_id)
                    if data.binary_chat_mode == 0:
                        sqlWorker.whitelist(self.reply_user_id, add=True)
                    sqlWorker.abuse_update(self.reply_user_id, force=True, timer=3600)
                    bot.reply_to(self.message, welcome_msg_get(self.reply_username, self.message))
                    return True
            except telebot.apihelper.ApiTelegramException:
                sqlWorker.remove_ally(ally_id[0])
        return False

    def whitelist_mode(self):
        until_date = int(time.time()) + 86400
        ban_text = "Пользователя нет в вайтлисте, он заблокирован на 1 сутки."
        if sqlWorker.whitelist(self.reply_user_id):
            sqlWorker.abuse_update(self.message.from_user.id, timer=3600, force=True)
            bot.reply_to(self.message, welcome_msg_get(self.reply_username, self.message))
            return
        try:
            bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=until_date)
            bot.reply_to(self.message, ban_text)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки вошедшего пользователя. Недостаточно прав?")

    def vote_mode(self):
        self.unique_id = str(self.reply_user_id) + "_new_usr"
        if self.is_voting_exist():
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
            return

        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 300
        self.vote_text = ("Требуется подтверждение вступления нового пользователя "
                          f"{html_fix(self.reply_username)}, "
                          f"в противном случае он будет кикнут на {formatted_timer(until_time)}")
        self.poll_maker(current_timer=900,
                        vote_args=[self.reply_username, self.reply_user_id, "пользователя", until_time])

    def captcha_mode(self):
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
            return

        data_list = sqlWorker.captcha(self.message.message_id, user_id=self.message.from_user.id)
        if data_list:
            bot.reply_to(self.message, "Капча уже существует.")
            return

        button_values = [random.randint(1000, 9999) for _ in range(3)]
        max_value = max(button_values)
        buttons = [types.InlineKeyboardButton(text=str(i), callback_data=f"captcha_{i}") for i in button_values]
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(*buttons)
        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 300
        bot_message = bot.reply_to(self.message, "\u26a0\ufe0f <b>СТОП!</b> \u26a0\ufe0f"  # Emoji
                                                 "\nВы были остановлены антиспам-системой TeleBOSS!\n"
                                                 "Для доступа в чат вам необходимо выбрать из списка МАКСИМАЛЬНОЕ "
                                                 "число в течении 60 секунд, иначе доступ в чат будет ограничен на "
                                                 f"срок {formatted_timer(until_time)} Время пошло.",
                                   reply_markup=keyboard, parse_mode="html")

        sqlWorker.captcha(bot_message.id, add=True, user_id=self.reply_user_id,
                          max_value=max_value, username=self.reply_username)
        threading.Thread(target=self.captcha_mode_failed, daemon=True,
                         args=(bot_message, until_time)).start()

    @staticmethod
    def captcha_mode_failed(bot_message, until_time):
        time.sleep(60)
        data_list = sqlWorker.captcha(bot_message.message_id)
        if not data_list:
            return
        sqlWorker.captcha(bot_message.message_id, remove=True)
        sqlWorker.abuse_update(data_list[0][1], until_time)
        try:
            bot.ban_chat_member(bot_message.chat.id, data_list[0][1], until_date=int(time.time()) + until_time)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.edit_message_text(f"Я не смог заблокировать пользователя {data_list[0][3]}! Недостаточно прав?",
                                  bot_message.chat.id, bot_message.message_id)
            return
        bot.edit_message_text(f"К сожалению, пользователь {data_list[0][3]} не смог пройти капчу и сможет войти в чат "
                              f"только через {formatted_timer(until_time)}",
                              bot_message.chat.id, bot_message.message_id)
