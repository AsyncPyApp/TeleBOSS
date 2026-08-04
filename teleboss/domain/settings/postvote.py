import json
import time

from teleboss.shared.parsers import formatted_timer
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PostVote


class Threshold(PostVote):
    votes_counter = ""
    threshold_type_text = ""
    ban = False
    minimum = False
    _description = "смена порога голосов"

    def post_vote_child(self):
        button_data = json.loads(self.records[4])
        counters_yes = 0
        counters_no = 0
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])
        self.ban = True if self.data_list[1] == "threshold_ban" else False
        self.minimum = True if self.data_list[1] == "threshold_min" else False
        if self.ban:
            self.threshold_type_text = "голосований по вопросам бана"
        elif self.minimum:
            self.threshold_type_text = "минимального количества голосов"
        else:
            self.threshold_type_text = "голосований по стандартным вопросам"
        if self.data_list[1] == "threshold_min":
            self.votes_counter = "\nЗа: " + str(counters_yes) + "\n" + "Против: " + str(counters_no)
        if counters_yes > counters_no and self.data_list[1] == "threshold_min":
            self.is_accept = True

    def accept(self):
        if self.data_list[0] == 0:
            data.thresholds_set(0, self.ban, self.minimum)
            bot.edit_message_text(f"Установлен автоматический порог {self.threshold_type_text}.\n"
                                  + "Теперь требуется минимум " + str(data.thresholds_get(self.ban))
                                  + " голосов для принятия решения." + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
        else:
            data.thresholds_set(self.data_list[0], self.ban, self.minimum)
            bot.edit_message_text(f"Установлен порог {self.threshold_type_text}: "
                                  + str(self.data_list[0]) + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос смены порога {self.threshold_type_text} отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Timer(PostVote):
    _description = "смена таймера для стандартных опросов"
    timer_text = ""

    def accept(self):
        data.timer_set(self.data_list[0])
        bot.edit_message_text("Установлен таймер основного голосования на "
                              + formatted_timer(self.data_list[0]) + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены таймера " + self.timer_text + "отклонён." + self.votes_counter,
                              self.message_vote_chat_id, self.message_vote_id)


class TimerBan(Timer):
    _description = "смена таймера для бан-опросов"
    timer_text = "для бана "

    def accept(self):
        data.timer_set(self.data_list[0], True)
        bot.edit_message_text("Установлен таймер голосования за бан на " + formatted_timer(self.data_list[0])
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class ChangeRate(PostVote):
    _description = "изменение рейтинга"

    def accept(self):
        button_data = json.loads(self.records[4])
        counters_yes = 0
        counters_no = 0
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])

        if self.data_list[2] == "up":
            ch_rate = "увеличил на " + str(counters_yes - counters_no)
            sqlWorker.update_rate(self.data_list[1], counters_yes - counters_no)
        else:
            ch_rate = "уменьшил на " + str(counters_yes - counters_no)
            sqlWorker.update_rate(self.data_list[1], counters_no - counters_yes)
        bot.edit_message_text(f"Пользователь {self.data_list[3]} "
                              f"{ch_rate} социальный рейтинг пользователя {self.data_list[0]}."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос изменения социального рейтинга пользователя {self.data_list[0]} отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Whitelist(PostVote):
    _description = "редактирование вайтлиста"

    def accept(self):
        if self.data_list[2] == "add":
            sqlWorker.whitelist(self.data_list[0], add=True)
            bot.edit_message_text(f"Пользователь {self.data_list[1]} добавлен в вайтлист."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        else:
            sqlWorker.whitelist(self.data_list[0], remove=True)
            bot.edit_message_text(f"Пользователь {self.data_list[1]} удалён из вайтлиста."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        if self.data_list[2] == "add":
            bot.edit_message_text(f"Вопрос добавления пользователя {self.data_list[1]} в вайтлист отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        else:
            bot.edit_message_text(f"Вопрос удаления пользователя {self.data_list[1]} из вайтлиста отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class PrivateMode(PostVote):
    _description = "изменение настроек приватности чата"

    def accept(self):
        if data.chat_mode != "mixed":
            bot.edit_message_text("Настройки приватности не могут быть перезаписаны (запрещено хостером бота!)"
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
            return
        data.binary_chat_mode = self.data_list[0]
        sqlWorker.params("public_mode", self.data_list[0])
        bot.edit_message_text(f"Пользователь {self.data_list[1]} изменил режим приватности чата на {self.data_list[2]}."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос изменения настроек приватности чата отклонён."
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Shield(PostVote):
    _description = "перенастройка защиты чата"

    def accept(self):
        sqlWorker.params("shield", rewrite_value=int(time.time()) + self.data_list[0])
        if self.data_list[0] == 0:
            bot.edit_message_text(f"Пользователь {self.data_list[1]} отключил режим защиты чата."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        else:
            bot.edit_message_text(f"Пользователь {self.data_list[1]} включил режим защиты чата на срок "
                                  f"{formatted_timer(self.data_list[0])}"
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        vote_type = "отключения" if self.data_list[0] == 0 else "включения"
        bot.edit_message_text(f"Предложение {vote_type} режима защиты чата отклонено!"
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class VotePrivacy(PostVote):
    _description = "изменение режима приватности голосований"
    _vote_privacy_text = {'private': 'приватный', 'public': 'публичный', 'hidden': 'скрытый'}

    def accept(self):
        sqlWorker.params("vote_privacy", rewrite_value=self.data_list[0])
        data.vote_privacy = self.data_list[0]
        bot.edit_message_text(f'Пользователь {self.data_list[1]} изменил режим приватности голосований на '
                              f'{self._vote_privacy_text[self.data_list[0]]}.'
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        bot.edit_message_text(f'Предложение изменить режим приватности голосований на '
                              f'{self._vote_privacy_text[self.data_list[0]]} отклонено.'
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class Marmalade(PostVote):
    _description = "изменение режима работы механизма защиты чата Marmalade"
    _vote_privacy_text = {'private': 'приватный', 'public': 'публичный', 'hidden': 'скрытый'}

    def accept(self):
        sqlWorker.params("marmalade", rewrite_value=self.data_list[0])
        marmalade_text = 'включил' if self.data_list[0] else 'отключил'
        bot.edit_message_text(f'Пользователь {self.data_list[1]} {marmalade_text} механизм защиты чата Marmalade.'
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        marmalade_text = 'включить' if self.data_list[0] else 'отключить'
        bot.edit_message_text(f'Предложение {marmalade_text} механизм защиты чата Marmalade отклонено.'
                              + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)


class RandomCooldown(PostVote):
    _description = "изменение кулдауна команды /random"

    def accept(self):
        sqlWorker.abuse_random(self.message_vote_chat_id, self.data_list[0])
        if self.data_list[0] == -1:
            bot.edit_message_text("Команда /random отключена." + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
        elif self.data_list[0] == 0:
            bot.edit_message_text("Кулдаун команды /random отключён." + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)
        else:
            bot.edit_message_text("Установлен порог кулдауна команды /random на значение " +
                                  formatted_timer(self.data_list[0]) + self.votes_counter,
                                  self.message_vote_chat_id, self.message_vote_id)

    def decline(self):
        if self.data_list[0] == -1:
            bot.edit_message_text(f"Вопрос отключения команды /random отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
        else:
            bot.edit_message_text(f"Вопрос изменения таймера команды /random отклонён."
                                  + self.votes_counter, self.message_vote_chat_id, self.message_vote_id)
