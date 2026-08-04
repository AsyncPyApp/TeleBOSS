import logging
import time

import telebot

from teleboss.shared.parsers import formatted_timer, html_fix
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PostVote


class UserAdd(PostVote):
    _description = "инвайт пользователя"
    mention = ""

    def post_vote_child(self):
        self.mention = f'<a href="tg://user?id={self.data_list[0]}">{html_fix(self.data_list[1])}</a>'

    def accept(self):
        sqlWorker.abuse_remove(self.data_list[2])
        sqlWorker.whitelist(self.data_list[2], add=True)
        chat_member = bot.get_chat_member(self.message_vote_chat_id, self.data_list[2])
        if not (chat_member.status in ["left", "kicked"] or
                (chat_member.status == "restricted" and not chat_member.is_member)):
            bot.edit_message_text("Пользователь " + self.mention + " уже есть в этом чате. Инвайт отправлен не будет."
                                  + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id, parse_mode="html")
            bot.send_message(self.data_list[0], "Вы уже есть в нужном вам чате. Повторный инвайт выдавать запрещено.")
            return

        try:
            invite = bot.create_chat_invite_link(self.message_vote_chat_id, expire_date=int(time.time()) + 86400)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка создания инвайт-ссылки для пользователя " + self.mention
                                  + "! Недостаточно прав?" + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id, parse_mode="html")
            bot.send_message(self.data_list[0], "Ошибка создания инвайт-ссылки для вступления.")
            raise e

        try:
            bot.unban_chat_member(self.message_vote_chat_id, self.data_list[2], only_if_banned=True)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'In func postvote.UserAdd.accept: {e}')

        bot.edit_message_text(f"Создана инвайт-ссылка и отправлена запросившему кандидату {self.mention}.\n"
                              f"Ссылка истечёт через 1 сутки." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id, parse_mode="html")

        bot.send_message(self.data_list[0], f"Дано добро на вступление в чат "
                                            f"{bot.get_chat(self.message_vote_chat_id).title}!\n"
                                            "Ссылка истечёт через 1 сутки.\n" + invite.invite_link)
        if data.rate:
            sqlWorker.update_rate(self.data_list[0], 0)

    def decline(self):
        sqlWorker.abuse_update(self.data_list[0])
        bot.edit_message_text(f"Запрос вступления пользователя {self.mention} был отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id,
                              parse_mode="html")

        bot.send_message(self.data_list[0], "Запрос на вступление был отклонён." + self.votes_counter)


class Ban(PostVote):
    _description = "блокировка пользователя"

    def accept(self):
        until_date = int(time.time()) + self.data_list[4] if self.data_list[4] != 0 else None
        if self.data_list[4] != 0:
            until_text = " на время " + formatted_timer(self.data_list[4])
        else:
            until_text = "."
        try:
            if bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).status == "administrator":
                bot.restrict_chat_member(self.message_vote_chat_id, self.data_list[0], None, can_send_messages=True)
            if self.data_list[3] == 2:
                if data.binary_chat_mode == 0:
                    sqlWorker.whitelist(self.data_list[0], remove=True)
                bot.ban_chat_member(self.message_vote_chat_id, self.data_list[0])
                bot.edit_message_text("Пользователь " + self.data_list[1] + " перманентно заблокирован "
                                      + "по милости пользователя " + self.data_list[2]
                                      + " и не сможет войти в чат до разблокировки."
                                      + self.data_list[5] + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)
                sqlWorker.clear_rate(self.data_list[0])
            elif self.data_list[3] == 1:
                bot.ban_chat_member(self.message_vote_chat_id, self.data_list[0], until_date=until_date)
                rate = "" if not self.change_rate(-10) else f"\nРейтинг {self.data_list[1]} снижен на 10 пунктов."
                bot.edit_message_text(f"Пользователь {self.data_list[1]} заблокирован в чате по милости пользователя "
                                      + self.data_list[2] + until_text + self.data_list[5] + rate
                                      + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

            elif self.data_list[3] == 0:
                bot.restrict_chat_member(self.message_vote_chat_id, self.data_list[0],
                                         can_send_messages=False, can_change_info=False,
                                         can_invite_users=False, can_pin_messages=False, until_date=until_date)
                rate = "" if not self.change_rate(-5) else f"\nРейтинг {self.data_list[1]} снижен на 5 пунктов."

                bot.edit_message_text("Пользователь " + self.data_list[1]
                                      + " лишён права переписки в чате по милости пользователя " + self.data_list[2]
                                      + until_text + self.data_list[5] + rate + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)

        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка блокировки пользователя " + self.data_list[1] + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
            raise e

    def decline(self):
        solution = ("ограничения", "кика", "блокировки")
        bot.edit_message_text("Вопрос " + solution[self.data_list[3]] + " " + self.data_list[1] + " отклонён"
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class UnBan(PostVote):
    _description = "снятие ограничений с пользователя"

    def accept(self):
        try:
            if (data.binary_chat_mode == 0 and
                    not bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).user.is_bot):
                sqlWorker.whitelist(self.data_list[0], add=True)
            sqlWorker.abuse_remove(self.data_list[0])
            bot.unban_chat_member(self.message_vote_chat_id, self.data_list[0], True)
            bot.restrict_chat_member(self.message_vote_chat_id, self.data_list[0], can_send_messages=True,
                                     can_change_info=True, can_invite_users=True, can_pin_messages=True,
                                     can_send_media_messages=True, can_send_polls=True,
                                     can_send_other_messages=True,
                                     can_add_web_page_previews=True)

            rate = "" if not self.change_rate(2) else f"\nРейтинг {self.data_list[1]} повышен на 2 пункта."
            bot.edit_message_text("Пользователю " + self.data_list[1] + " восстановлено право переписки в чате "
                                  + "по милости пользователя " + self.data_list[2] + rate
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Я не смог вынести из мута пользователя " + self.data_list[1]
                                  + ".  Недостаточно прав?" + self.votes_counter, self.message_vote_chat_id,
                                  self.message_vote_id)
            raise e

    def decline(self):
        bot.edit_message_text("Вопрос снятия ограничений с пользователя " + self.data_list[1] + " отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Captcha(PostVote):
    _description = "капча"

    def accept(self):
        sqlWorker.abuse_update(self.data_list[1], timer=3600, force=True)
        try:
            bot.restrict_chat_member(self.message_vote_chat_id, self.data_list[1],
                                     None, True, True, True, True, True, True, True, True)
            if data.binary_chat_mode == 0: # For Marmalade
                sqlWorker.whitelist(self.data_list[1], add=True)
            sqlWorker.marmalade_remove(self.data_list[1])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(f"Я не смог снять ограничения с {self.data_list[2]} {self.data_list[0]}! "
                                  f"Недостаточно прав?", self.message_vote_chat_id, self.message_vote_id)
            raise e
        bot.edit_message_text(f"Вступление {self.data_list[2]} {self.data_list[0]} одобрено!" + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        sqlWorker.abuse_update(self.data_list[1], timer=self.data_list[3])
        try:
            bot.ban_chat_member(self.message_vote_chat_id, self.data_list[1],
                                until_date=int(time.time()) + self.data_list[3])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(f"Я не смог заблокировать {self.data_list[2]} {self.data_list[0]}! "
                                  f"Недостаточно прав?", self.message_vote_chat_id, self.message_vote_id)
            raise e
        bot.edit_message_text(f"Вступление {self.data_list[2]} {self.data_list[0]} отклонено.\n" +
                              f"Следующая попытка будет возможна через {formatted_timer(self.data_list[3])}" +
                              self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class DelMessage(PostVote):
    _description = "удаление сообщения"

    def accept(self):
        try:
            bot.delete_message(self.message_vote_chat_id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            if "message to delete not found" in str(e):
                bot.edit_message_text("Сообщение, которое требуется удалить, не найдено." + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)
            else:
                bot.edit_message_text("Ошибка удаления сообщения по голосованию." + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)
            self.data_list[2] = False  # Disable silent mode
            raise e

        if self.data_list[2]:
            try:
                bot.delete_message(self.message_vote_chat_id, self.message_vote_id)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'In func postvote.DelMessage.accept: {e}')
        else:
            bot.edit_message_text("Сообщение пользователя " + self.data_list[1] + " удалено успешно."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text("Вопрос удаления сообщения отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)

    def final_hook(self, error=False):
        if self.data_list[2]:
            return
        super().final_hook(error)
