import logging
import time
import traceback
import zlib
from typing import Optional

import telebot

from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    time_parser,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote


class Rules(PreVote):
    unique_id = "rules"
    help_text = "Используйте аргументы add (с реплеем по сообщению с текстом правил) для добавления правил, " \
                "remove - для их удаления."

    def pre_return(self) -> Optional[bool]:
        if self.message.chat.id != data.main_chat_id and self.message.chat.id != self.message.from_user.id:
            bot.reply_to(self.message, "Данную команду можно запустить только в основном чате или в ЛС без аргументов.")
            return True

        if self.message.from_user.id == self.message.chat.id:
            if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                bot.reply_to(self.message, "У вас нет прав использовать эту команду.")
                return True
            if extract_arg(self.msg_txt, 1) is not None:
                bot.reply_to(self.message, "Данную команду в ЛС можно запустить только без аргументов.")
                return True
        return None

    def direct_fn(self):
        if data.fixed_rules:
            try:
                rules_text = open(data.path + "rules.txt", encoding="utf-8").read()
            except FileNotFoundError:  # No file = no rules!
                bot.reply_to(self.message, "В чате нет правил!")
                return
            except IOError:
                logging.error(traceback.format_exc())
                bot.reply_to(self.message, "Файл rules.txt не читается!")
                return
        else:
            rules_text = sqlWorker.params("rules", default_return="")
            if rules_text == "":
                bot.reply_to(self.message, "В чате нет правил!")
                return

        try:
            bot.send_message(self.message.from_user.id, f"<b>Правила чата:</b>\n{rules_text}", parse_mode="html")
            if self.message.from_user.id != self.message.chat.id:
                bot.reply_to(self.message, "Текст правил чата отправлен в л/с.")
        except telebot.apihelper.ApiTelegramException:
            bot.reply_to(self.message,
                         "Я не смог отправить сообщение вам в л/с. Недостаточно прав или нет личного диалога?")

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def help(self):
        if not self.help_access_check():
            return
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        bot.reply_to(self.message, self.help_text, parse_mode="html")

    def add(self):
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        if self.message.reply_to_message is None:
            bot.reply_to(self.message, "Пожалуйста, используйте эту команду как ответ на текстовое сообщение.")
            return

        if self.message.reply_to_message.text is None:
            bot.reply_to(self.message, "В отвеченном сообщении не обнаружен текст!")
            return
        self.vote_type = "add rules"
        self.pre_vote("добавление", self.message.reply_to_message.text)

    def remove(self):
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        rules_text = sqlWorker.params("rules", default_return="")
        if rules_text == "":
            bot.reply_to(self.message, "В чате нет правил!")
            return
        self.vote_type = "remove rules"
        self.pre_vote("удаление", rules_text)

    def pre_vote(self, vote_type_text, rules_text):
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: {vote_type_text} правил.\nТекст правил:\n"
                          f"<b>{html_fix(rules_text)}</b>"
                          f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [rules_text, username_parser(self.message)]
        self.poll_maker()


class CustomPoll(PreVote):
    vote_type = "custom poll"
    help_text = 'Используйте эту команду для создания опросов в стиле TeleBOSS.\n' \
                'Первым аргументом может быть парсимое время (подробнее см. /help).\n' \
                'Если аргумент времени не парсится, длительность опроса будет 1 сутки.\n' \
                'Если кроме аргумента времени текста больше нет, аргумент будет считаться текстом.\n' \
                'Если в конце текста идёт одна или несколько строк, начинающихся с символа "#" ' \
                'и пробела, то опрос считается кастомным, и каждая такая строка является пунктом ответа.\n' \
                'Опрос закрывается по завершении таймера или после набора голосов всех участников.'
    options_list: list

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message, True):
            return True
        self.options_list = []
        return None

    @staticmethod
    def timer_votes_init():
        """timer, votes"""
        return 86400, 0  # For custom poll, the upper threshold of votes is the sum of participants

    def direct_fn(self):
        self.help()

    def get_votes_text(self):
        return f"{self.vote_text}\nОпрос будет закрыт через {formatted_timer(self.current_timer)}, " \
               f"после голосования всех участников чата или при закрытии вручную."

    def help_access_check(self):
        return True

    def arg_fn(self, arg):
        self.options_list = []
        poll_timer = time_parser(arg)
        if poll_timer is None:
            poll_text = self.msg_txt.split(maxsplit=1)[1]
        else:
            if extract_arg(self.msg_txt, 2) is None:
                poll_text = arg
            else:
                poll_text = self.msg_txt.split(maxsplit=2)[2]
                self.current_timer = poll_timer
        if not 300 <= self.current_timer <= 86400:
            bot.reply_to(self.message, "Время опроса не может быть меньше 5 минут и больше 1 суток.")
            return
        self.unique_id = f"custom_{zlib.crc32(poll_text.encode('utf-8'))}_{self.message.chat.id}"
        if self.is_voting_exist():
            return

        parsed_text = poll_text.split(sep="\n")
        poll_text = ""
        for poll_str in parsed_text:
            if not poll_str.split(maxsplit=1):
                continue
            elif poll_str.split(maxsplit=1)[0] == "#":
                try:
                    poll_point = poll_str.split(maxsplit=1)[1]
                except IndexError:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Пустой вариант в списке!")
                    return
                if poll_point in self.options_list:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Дублирующий вариант в списке!")
                    return
                elif len(poll_point) > 30:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Кнопка не вмещает более 30 символов!\n"
                                               f"(строка {poll_point})")
                    return
                self.options_list.append(poll_point)
            elif self.options_list:
                bot.reply_to(self.message, "Ошибка парсинга опроса! Варианты должны идти в конце текста!")
                return
            else:
                poll_text += poll_str + "\n"

        if len(self.options_list) > 15:
            bot.reply_to(self.message, "Ошибка парсинга опроса! Вариантов не может быть больше 15-ти!")
            return
        if poll_text == "":
            bot.reply_to(self.message, "Ошибка парсинга опроса! Отсутствует заголовок опроса!")
            return
        poll_text = poll_text[:-1]
        self.vote_text = (f"Текст опроса: <b>{html_fix(poll_text)}</b>"
                          f"\nИнициатор опроса: {username_parser(self.message, True)}.")
        custom_poll = True if self.options_list else False
        self.vote_args = [poll_text, int(time.time()), custom_poll]
        self.poll_maker()

    # noinspection PyTypeChecker
    # Совсем этот пучарм обурел
    # С++ хотя бы не пытается делать вид, что он умнее прогера на нём
    # (Поскольку для кодинга на C++ нужны яйца, а у меня их нет)
    def get_buttons_scheme(self):
        if not self.options_list:
            button_scheme = [{"button_type": f"vote!_{i}", "name": i, "user_list": []} for i in ("Да", "Нет")]
        else:
            button_scheme = [{"button_type": f"vote!_{i}", "name": i, "user_list": []} for i in self.options_list]
            button_scheme.append({"button_type": "row_width", "row_width": 1})  # Меня вынудили.
        if self.privacy == 'public':
            button_scheme.append({"button_type": "user_votes",
                                  "name": "Список голосов"})
        else:
            button_scheme.append({"button_type": "my_vote",
                                  "name": "Узнать мой голос"})
        if self.user_id != data.ANONYMOUS_ID:
            button_scheme.append({"button_type": "close", "name": "Закрыть опрос", "user_id": self.user_id})
        return button_scheme
