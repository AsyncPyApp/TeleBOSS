import logging
import threading
from typing import Optional
import telebot
from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    html_fix,
    reply_msg_target,
    topic_reply_fix,
    username_parser,
    username_parser_chat_member,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class Whitelist(PreVote):
    vote_type = "whitelist"

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True
        if data.binary_chat_mode != 0:
            bot.reply_to(self.message, "Вайтлист в данном режиме отключён (см. команду /private).")
            return True
        if extract_arg(self.msg_txt, 1) in ("add", "remove"):
            if topic_reply_fix(self.message.reply_to_message) is not None:
                self.reply_user_id, self.reply_username, self.reply_is_bot = \
                    reply_msg_target(self.message.reply_to_message)
            else:
                self.reply_user_id, self.reply_username, self.reply_is_bot = reply_msg_target(self.message)
        return None

    def direct_fn(self):
        user_whitelist = sqlWorker.whitelist_get_all()
        if not user_whitelist:
            bot.reply_to(self.message, "Вайтлист данного чата пуст!")
            return

        threading.Thread(target=self.whitelist_building, args=(user_whitelist,)).start()

    def whitelist_building(self, user_whitelist):
        whitelist_msg = bot.reply_to(self.message, "Сборка вайтлиста, ожидайте...")
        user_list, counter = "Список пользователей, входящих в вайтлист:\n", 0
        for user in user_whitelist:
            try:
                username = username_parser_chat_member(bot.get_chat_member(data.main_chat_id,
                                                                                 user[0]), html=True)
                if username == "":
                    raise IndexError("Nickname is empty!")
            except (telebot.apihelper.ApiTelegramException, IndexError) as e:
                logging.error(f'Error adding participant with id {user} to whitelist!\n{e}')
                sqlWorker.whitelist(user[0], remove=True)
                continue
            counter += 1
            user_list = user_list + f'{counter}. <a href="tg://user?id={user[0]}">{username}</a>\n'

        if counter == 0:
            bot.edit_message_text("Вайтлист данного чата пуст!",
                                  chat_id=whitelist_msg.chat.id, message_id=whitelist_msg.id, parse_mode='html')
            return

        bot.edit_message_text(f"{user_list}Узнать подробную информацию о "
                              f"конкретном пользователе можно командой /status",
                              chat_id=whitelist_msg.chat.id, message_id=whitelist_msg.id, parse_mode='html')

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def add(self):
        is_whitelist = sqlWorker.whitelist(self.reply_user_id)
        if is_whitelist:
            bot.reply_to(self.message, f"Пользователь {self.reply_username} уже есть в вайтлисте!")
            return
        self.add_remove(f"добавление пользователя {html_fix(self.reply_username)} в вайтлист")

    def remove(self):
        if extract_arg(self.msg_txt, 2) is not None:
            self.index_remove()
            return
        is_whitelist = sqlWorker.whitelist(self.reply_user_id)
        if not is_whitelist:
            bot.reply_to(self.message, f"Пользователя {self.reply_username} нет в вайтлисте!")
            return
        self.add_remove(f"удаление пользователя {html_fix(self.reply_username)} из вайтлиста")

    def add_remove(self, whitelist_text):
        if self.reply_user_id in [data.bot_id, data.ANONYMOUS_ID]:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return
        elif self.reply_is_bot:
            bot.reply_to(self.message, f"Вайтлист не работает для ботов!")
            return
        self.pre_vote(whitelist_text)

    def index_remove(self):
        user_whitelist = sqlWorker.whitelist_get_all()
        if not user_whitelist:
            bot.reply_to(self.message, "Вайтлист данного чата пуст!")
            return

        try:
            index = int(extract_arg(self.msg_txt, 2)) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Индекс должен быть больше нуля.")
            return

        try:
            self.reply_user_id = user_whitelist[index][0]
        except IndexError:
            bot.reply_to(self.message, "Пользователь с данным индексом не найден в вайтлисте!")
            return

        try:
            self.reply_username = username_parser_chat_member(bot.get_chat_member(data.main_chat_id,
                                                                                        self.reply_user_id), html=True)
            if self.reply_username == "":
                sqlWorker.whitelist(self.reply_user_id, remove=True)
                bot.reply_to(self.message, "Удалена некорректная запись!")
                return
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error when deleting a member from the whitelist by index!\n{e}')
            sqlWorker.whitelist(self.reply_user_id, remove=True)
            bot.reply_to(self.message, "Удалена некорректная запись!")
            return

        self.pre_vote(f"удаление пользователя {self.reply_username} из вайтлиста")

    def pre_vote(self, whitelist_text):

        self.unique_id = str(self.reply_user_id) + "_whitelist"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: {whitelist_text}.\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username, extract_arg(self.msg_txt, 1)]
        self.poll_maker()
