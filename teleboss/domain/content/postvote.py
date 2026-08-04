import json
import logging
import time
import traceback

import telebot

from teleboss.shared.parsers import formatted_timer, html_fix
from teleboss.shared.runtime import bot, sqlWorker
from teleboss.voting.bases import PostVote


class AddRules(PostVote):
    _description = "добавление правил"

    def accept(self):
        sqlWorker.params("rules", self.data_list[0])
        bot.edit_message_text(f"Пользователь {html_fix(self.data_list[1])} установил следующие правила чата:\n"
                              f"<b>{html_fix(self.data_list[0])}</b>" + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id, parse_mode="html")

    def decline(self):
        bot.edit_message_text(f"Вопрос добавления правил отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class RemoveRules(PostVote):
    _description = "удаление правил"

    def accept(self):
        sqlWorker.params("rules", "")
        bot.edit_message_text(f"Пользователь {self.data_list[1]} удалил правила чата!"
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос удаления правил отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class CustomPoll(PostVote):
    _description = "пользовательский опрос"

    def post_vote(self, records):
        self.data_list = json.loads(records[6])
        self.message_vote_id = records[1]
        self.message_vote_chat_id = records[3]
        votes_private = True
        button_data = json.loads(records[4])
        for button in button_data:
            if button["button_type"] == "user_votes":
                votes_private = False

        counters_yes = 0
        counters_no = 0
        if self.data_list[2]:
            self.votes_counter = "\nГолоса за варианты ответа:"
            for button in button_data:
                if 'vote!' in button["button_type"]:
                    if votes_private:
                        self.votes_counter += f'\n{button["name"]} - {len(button["user_list"])}'
                    else:
                        self.votes_counter += f'\n{button["name"]} - {self.get_voted_usernames(button["user_list"])}'
        else:
            for button in button_data:
                if 'vote!' in button["button_type"]:
                    if button["name"] == "Да":
                        if votes_private:
                            counters_yes = len(button["user_list"])
                        else:
                            counters_yes = self.get_voted_usernames(button["user_list"])
                    elif button["name"] == "Нет":
                        if votes_private:
                            counters_no = len(button["user_list"])
                        else:
                            counters_no = self.get_voted_usernames(button["user_list"])
            self.votes_counter = f"\nЗа: {counters_yes}\nПротив: {counters_no}"
        self.records = records
        self.accept()
        self.final_hook()

    def accept(self):
        bot.edit_message_text(f"Опрос завершён. Текст опроса: <b>{html_fix(self.data_list[0])}</b>" +
                              f"\nДлительность опроса - {formatted_timer(int(time.time()) - self.data_list[1])}" +
                              self.votes_counter, self.message_vote_chat_id, self.message_vote_id,
                              parse_mode="html")

    def final_hook(self, error=False):
        try:
            bot.unpin_chat_message(self.message_vote_chat_id, self.message_vote_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't unpin message in chat {self.message_vote_chat_id}!\n{e}")
        try:
            bot.send_message(self.message_vote_chat_id, "Опрос завершён!", reply_to_message_id=self.message_vote_id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
