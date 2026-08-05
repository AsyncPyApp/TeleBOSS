import json
import logging
import os
import time
import traceback

import telebot

from teleboss.shared.access import allowed_list
from teleboss.shared.parsers import html_fix
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PostVote
from teleboss.voting.exceptions import InternalBotException, SilentException


class GlobalOp(PostVote):
    _description = "изменение разрешённых прав для выдачи"

    def accept(self):
        if data.admin_fixed:
            bot.edit_message_text("Настройки выдачи прав администратора не могут быть перезаписаны "
                                  "(запрещено хостером бота!)"
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            return

        data.admin_allowed = self.data_list[0]
        if not data.admin_fixed:
            sqlWorker.params("allowed_admins", self.data_list[0])
        bot.edit_message_text("Разрешённые для администраторов права успешно изменены на следующие:\n"
                              + allowed_list() + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)
        return

    def decline(self):
        bot.edit_message_text("Вопрос изменения разрешённых для администраторов прав отклонён" + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class OpSetup(PostVote):
    _description = "чек-лист выбора прав администратора"

    def post_vote(self, records):
        self.data_list = json.loads(records[6])
        self.message_vote_id = records[1]
        self.message_vote_chat_id = records[3]
        button_data = json.loads(records[4])
        for button in button_data:
            if button["button_type"] == "op!_confirmed":
                if button["value"]:
                    return
        by_timer = "инициатором голосования" if int(time.time()) <= records[5] else "автоматическим таймером"
        bot.edit_message_text(f"<b>Чек-лист закрыт {by_timer}.</b>", self.message_vote_chat_id,
                              self.message_vote_id, parse_mode='html', reply_markup=None)


class GlobalOpSetup(OpSetup):
    _description = "чек-лист выбора глобальных прав"


class Op(PostVote):
    _description = "назначение администратора"

    def accept(self):
        status = bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).status
        if status not in ("member", "administrator"):
            bot.edit_message_text(f"Пользователь {self.data_list[1]} имеет статус, "
                                  f"не позволяющий назначить его администратором."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            raise InternalBotException(f'User {self.data_list[1]} is not a member or administrator.')
        try:
            bot.promote_chat_member(self.message_vote_chat_id, self.data_list[0], **self.data_list[2])
            if not bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).user.is_bot:
                sqlWorker.whitelist(self.data_list[0], add=True)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(
                f"Ошибка назначения администратора {self.data_list[1]}. Недостаточно прав?" + self.votes_counter,
                self.message_vote_chat_id, self.message_vote_id)
            raise e

        rate = ""
        if status != "administrator":
            if self.change_rate(3):
                rate = f"\nРейтинг {self.data_list[1]} повышен на 3 пункта."

        bot.edit_message_text("Пользователь " + self.data_list[1] + " назначен администратором в чате."
                              + rate + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(
            "Вопрос назначения " + self.data_list[1] + " администратором отклонён." + self.votes_counter,
            self.message_vote_chat_id, self.message_vote_id)

    def final_hook(self, error=False):
        try:
            bot.unpin_chat_message(self.message_vote_chat_id, self.message_vote_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't unpin message in chat {self.message_vote_chat_id}!\n{e}")
        try:
            if error:
                bot.send_message(self.message_vote_chat_id,
                                 "Голосование завершено с ошибками. Информация сохранена в логи бота.",
                                 reply_to_message_id=self.message_vote_id)
            elif self.is_accept and not bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).user.is_bot:
                bot.send_message(self.message_vote_chat_id,
                                 f'Голосование завершено! <a href ="tg://user?id={self.data_list[0]}">'
                                 f'{html_fix(self.data_list[1])}</a>, пожалуйста, не забудь сменить звание!',
                                 reply_to_message_id=self.message_vote_id, parse_mode='html')
            else:
                bot.send_message(self.message_vote_chat_id, "Голосование завершено!",
                                 reply_to_message_id=self.message_vote_id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())


class Rank(PostVote):
    _description = "смена звания бота"

    def accept(self):
        if bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).status == "administrator":
            try:
                bot.set_chat_administrator_custom_title(self.message_vote_chat_id, self.data_list[0], self.data_list[2])
                bot.edit_message_text("Звание \"" + self.data_list[2] + "\" успешно установлено для бота "
                                      + self.data_list[1] + " пользователем " + self.data_list[
                                          3] + "." + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.edit_message_text("Ошибка смены звания для бота " + self.data_list[1]
                                          + " - в звании не поддерживаются эмодзи." + self.votes_counter,
                                          self.message_vote_chat_id, self.message_vote_id)
                    return
                bot.edit_message_text("Ошибка смены звания для бота " + self.data_list[1] + "." + self.votes_counter,
                                      self.message_vote_chat_id, self.message_vote_id)
                raise e
        else:
            bot.edit_message_text("Бот " + self.data_list[1] + " не является администратором. Смена звания невозможна."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены звания бота " + self.data_list[1] + " отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class Deop(PostVote):
    _description = "снятие администратора"

    def accept(self):
        if bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).status != "administrator":
            bot.edit_message_text("Пользователь " + self.data_list[1] + " уже не является администратором."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            return
        try:
            bot.promote_chat_member(self.message_vote_chat_id, self.data_list[0], can_manage_chat=False)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка снятия администратора " + self.data_list[1] + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
            raise e

        rate = "" if not self.change_rate(-3) else f"\nРейтинг {self.data_list[1]} снижен на 3 пункта."

        bot.edit_message_text("Пользователь " + self.data_list[1] + " разжалован из администраторов."
                              + rate + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text("Вопрос снятия " + self.data_list[1] + " из администраторов отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Title(PostVote):
    _description = "смена названия чата"

    def accept(self):
        try:
            bot.set_chat_title(self.message_vote_chat_id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки названия чата. Недостаточно прав?" + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
            raise e
        bot.edit_message_text("Название чата успешно сменено на \"" + self.data_list[0]
                              + "\" пользователем " + self.data_list[1] + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены названия чата отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class Description(PostVote):
    _description = "смена описания чата"

    def accept(self):
        try:
            bot.set_chat_description(self.message_vote_chat_id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки описания чата. Недостаточно прав?" + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
            raise e
        if self.data_list[0] == "":
            bot.edit_message_text("Описание чата успешно сменено на пустое пользователем "
                                  + self.data_list[1] + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
        else:
            bot.edit_message_text("Описание чата успешно сменено на\n<code>" + html_fix(self.data_list[0])
                                  + "</code>\nпользователем " + self.data_list[1] + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id, parse_mode="html")

    def decline(self):
        bot.edit_message_text("Вопрос смены описания чата отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class ChatPic(PostVote):
    _description = "смена аватарки чата"

    def accept(self):
        try:
            bot.set_chat_photo(self.message_vote_chat_id, open(data.path + 'tmp_img', 'rb'))
            bot.edit_message_text("Фотография чата успешно изменена пользователем " + self.data_list[0]
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        except Exception as e:
            bot.edit_message_text("Ошибка установки новой фотографии чата." + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
            raise e

    def decline(self):
        bot.edit_message_text("Вопрос смены фотографии чата отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def final_hook(self, error=False):
        try:
            os.remove(data.path + "tmp_img")
        except IOError:
            logging.error(traceback.format_exc())
        super().final_hook(error)


class Topic(PostVote):
    _description = "удаление топика"

    def accept(self):
        try:
            bot.delete_forum_topic(data.main_chat_id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка удаления топика! Информация сохранена в логах бота."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            raise e
        try:
            bot.send_message(data.main_chat_id, f"Пользователь {self.data_list[1]} удалил топик {self.data_list[2]}."
                             + self.votes_counter, message_thread_id=data.thread_id)
        except telebot.apihelper.ApiTelegramException:
            pass
        raise SilentException

    def decline(self):
        bot.edit_message_text(f"Вопрос удаления топика отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)
