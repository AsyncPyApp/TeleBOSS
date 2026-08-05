import logging
import random
import threading
import time
import telebot
from telebot import types
from teleboss.shared.access import welcome_msg_get
from teleboss.shared.parsers import (
    formatted_timer,
    html_fix,
    username_parser,
    username_parser_invite,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

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
