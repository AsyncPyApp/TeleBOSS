import telebot

from teleboss.shared.parsers import html_fix
from teleboss.shared.runtime import bot, sqlWorker
from teleboss.voting.bases import PostVote


class AddAllies(PostVote):
    _description = "добавление союзного чата"

    def accept(self):
        sqlWorker.abuse_update(self.data_list[0], force=True)
        sqlWorker.add_ally(self.data_list[0])
        try:
            ally_title = bot.get_chat(self.data_list[0]).title
            invite = bot.get_chat(self.data_list[0]).invite_link
            if invite is None:
                invite = "Инвайт-ссылка на данный чат отсутствует."
            else:
                invite = f"Инвайт ссылка на данный чат: {invite}."
            invite_main = bot.get_chat(self.message_vote_chat_id).invite_link
            if invite_main is None:
                invite_main = "Ссылка для упрощённого перехода отсутствует (недостаточно прав в основном чате?)"
            else:
                invite_main = f"Ссылка для упрощённого перехода: {invite_main}"
            bot.send_message(self.data_list[0], f"Установлены союзные отношения с чатом <b>"
                                                f"{html_fix(bot.get_chat(self.message_vote_chat_id).title)}"
                                                f"</b>!\n{invite_main}",
                             parse_mode="html", message_thread_id=self.data_list[1])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки союзных отношений с чатом! Информация сохранена в логах бота."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            raise e

        bot.edit_message_text(f"Установлены союзные отношения с чатом "
                              f"<b>{html_fix(ally_title)}!</b>\n{invite}"
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id,
                              parse_mode="html")

    def decline(self):
        sqlWorker.abuse_update(self.data_list[0])
        try:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом "
                                  f"{bot.get_chat(self.data_list[0]).title} отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            bot.send_message(self.data_list[0],
                             f"Вопрос установки союзных отношений с чатом "
                             f"{bot.get_chat(self.message_vote_chat_id).title} отклонён."
                             + self.votes_counter, message_thread_id=self.data_list[1])
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class RemoveAllies(PostVote):
    _description = "удаление союзного чата"

    def accept(self):
        sqlWorker.abuse_remove(self.data_list[0])
        sqlWorker.remove_ally(self.data_list[0])
        try:
            ally_title = f" <b>{html_fix(bot.get_chat(self.data_list[0]).title)}</b> "
            if self.data_list[2]:
                bot.send_message(
                    self.data_list[0],
                    f"Cоюз с чатом <b>{html_fix(bot.get_chat(self.message_vote_chat_id).title)}</b> разорван." +
                    self.votes_counter, parse_mode="html", message_thread_id=self.data_list[1]
                )
        except telebot.apihelper.ApiTelegramException:
            ally_title = " "
        bot.edit_message_text(f"Союзные отношения с чатом{ally_title}разорваны." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id, parse_mode="html")

    def decline(self):
        try:
            bot.edit_message_text(f"Вопрос разрыва союзных отношений с чатом "
                                  f"{bot.get_chat(self.data_list[0]).title} отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            if self.data_list[2]:
                bot.send_message(self.data_list[0],
                                 f"Вопрос разрыва союзных отношения с чатом "
                                 f"{bot.get_chat(self.message_vote_chat_id).title} отклонён." + self.votes_counter)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос разрыва союзных отношения с чатом отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
