import logging
import threading
from typing import Optional
import telebot
from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    html_fix,
    reply_msg_target,
    topic_reply_fix,
    username_parser,
    username_parser_chat_member,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class Rating(PreVote):
    help_text = "Доступны аргументы top, up, down и команда без аргументов."
    vote_type = "change rate"

    def pre_return(self) -> Optional[bool]:
        if not data.rate or command_forbidden(self.message):
            return True
        return None

    def direct_fn(self):
        if topic_reply_fix(self.message.reply_to_message) is None:
            user_id, username, _ = reply_msg_target(self.message)
            if user_id == data.ANONYMOUS_ID:
                bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
                return
        else:
            if self.message.reply_to_message.from_user.id in [data.bot_id, data.ANONYMOUS_ID]:
                bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
                return

            user_status = bot.get_chat_member(data.main_chat_id, self.message.reply_to_message.from_user.id).status

            if user_status == "kicked" or user_status == "left":
                sqlWorker.clear_rate(self.message.reply_to_message.from_user.id)
                bot.reply_to(self.message, "Этот пользователь не является участником чата.")
                return

            user_id, username, is_bot = reply_msg_target(self.message.reply_to_message)
            if is_bot:
                bot.reply_to(self.message, "У ботов нет социального рейтинга!")
                return

        user_rate = sqlWorker.get_rate(user_id)
        bot.reply_to(self.message, f"Социальный рейтинг пользователя {username}: {user_rate}")
        return

    def set_args(self) -> dict:
        return {"top": self.top, "up": self.up, "down": self.down}

    def up(self):
        mode = "up"
        mode_text = "увеличение"
        self.pre_vote(mode, mode_text)

    def down(self):
        mode = "down"
        mode_text = "уменьшение"
        self.pre_vote(mode, mode_text)

    def pre_vote(self, mode, mode_text):
        if self.message.reply_to_message is None:
            bot.reply_to(self.message, "Пожалуйста, ответьте на сообщение пользователя, "
                                       "чей социальный рейтинг вы хотите изменить")
            return

        self.reply_msg_target()

        if self.reply_user_id == self.message.from_user.id:
            bot.reply_to(self.message, "Вы не можете менять свой собственный рейтинг!")
            return

        if self.reply_user_id in [data.bot_id, data.ANONYMOUS_ID]:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if self.reply_is_bot:
            bot.reply_to(self.message, "У ботов нет социального рейтинга!")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status in ("kicked", "left"):
            sqlWorker.clear_rate(self.reply_user_id)
            bot.reply_to(self.message, "Этот пользователь не является участником чата.")
            return

        self.unique_id = str(self.reply_user_id) + "_rating_" + mode
        if self.is_voting_exist():
            return

        self.vote_text = (f"Тема голосования: {mode_text} "
                          f"социального рейтинга пользователя {html_fix(self.reply_username)}"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_username, self.message.reply_to_message.from_user.id,
                          mode, username_parser(self.message)]
        self.poll_maker()

    def top(self):
        threading.Thread(target=self.rate_top).start()

    def rate_top(self):
        rate_msg = bot.reply_to(self.message, "Сборка рейтинга, ожидайте...")
        rates = sqlWorker.get_all_rates()
        if rates is None:
            bot.edit_message_text("Ещё ни у одного пользователя нет социального рейтинга!",
                                  rate_msg.chat.id, rate_msg.id)
            return
        rates = sorted(rates, key=lambda rate: rate[1], reverse=True)
        rate_text = "Список пользователей по социальному рейтингу:"
        user_counter = 1

        for user_rate in rates:
            try:
                if bot.get_chat_member(data.main_chat_id, user_rate[0]).status in ["kicked", "left"]:
                    sqlWorker.clear_rate(user_rate[0])
                    continue
                username = username_parser_chat_member(bot.get_chat_member(data.main_chat_id, user_rate[0]), True)
                rate_text = rate_text + f'\n{user_counter}. ' \
                                        f'<a href="tg://user?id={user_rate[0]}">{username}</a>: {str(user_rate[1])}'
                user_counter += 1
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error getting user information with ID {user_rate[0]} while assembling rating table. '
                              f'His rating will be cleared.\n{e}')
                sqlWorker.clear_rate(user_rate[0])
                continue

        bot.edit_message_text(rate_text, chat_id=rate_msg.chat.id,
                              message_id=rate_msg.id, parse_mode='html')
