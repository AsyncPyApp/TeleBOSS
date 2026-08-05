import logging
import time
from typing import Optional
import telebot
from teleboss.shared.parsers import (
    formatted_timer,
    html_fix,
    username_parser,
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
