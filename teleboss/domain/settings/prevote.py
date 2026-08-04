import logging
import threading
import time
from typing import Optional

import telebot

from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    reply_msg_target,
    time_parser,
    topic_reply_fix,
    username_parser,
    username_parser_chat_member,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote
from teleboss.voting.engine import poll_engine


class Thresholds(PreVote):
    vote_type = "threshold"
    help_text = ('Используйте команду в формате "/threshold [(число)|auto] [(пустое)|ban|min]."\n'
                 'Примеры: /threshold auto ban, /threshold 5 min, /threshold auto.\n'
                 'Если число голосов для досрочного стандартных или бан-голосований оказывается ниже минимального '
                 'порога, оно автоматически приравнивается к минимальному порогу.\n\n'
                 'Автоматический порог высчитывается по нижеследующей схеме.\n'
                 'Для досрочного завершения стандарных голосований:\n- количество участников, делённое на 2 нацело, '
                 'но всегда меньше 8 и больше 2 и никогда не ниже значения минимального порога\n'
                 'Для досрочного завершения бан-голосований:\n- 5 при количестве участников больше 15,\n- 3 при '
                 'количестве участников больше 5\n- 2 в ином случае, но никогда не ниже минимального порога\n'
                 'Для минимального порога принятия результатов голосования:\n- 5 при количестве '
                 'участников больше 30\n- 3 при количестве участников больше 15\n- 2 в ином случае')

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True
        return None

    @staticmethod
    def auto_thr_text(bool_):
        return " (авто)" if bool_ else ""

    def direct_fn(self):

        bot.reply_to(
            self.message,
            "<b>Текущие пороги количества голосов:</b>\n"
            "Голосов для досрочного закрытия обычного голосования требуется (за любой вариант): "
            f"{data.thresholds_get()}{self.auto_thr_text(data.is_thresholds_auto())}\n"
            "Голосов для досрочного закрытия бан-голосования требуется (за любой вариант): "
            f"{data.thresholds_get(ban=True)}{self.auto_thr_text(data.is_thresholds_auto(ban=True))}\n"
            "Суммарный минимальный порог голосов, требуемый для принятия решения: "
            f"{data.thresholds_get(minimum=True)}{self.auto_thr_text(data.is_thresholds_auto(minimum=True))}",
            parse_mode='html'
        )

    def get_votes_text(self):
        if self.unique_id == "threshold_min":
            return f"{self.vote_text}\nГолосование будет закрыто через {formatted_timer(self.current_timer)}, " \
                   f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}."

        return f"{self.vote_text}\nГолосование будет закрыто через {formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def arg_fn(self, arg):
        if arg != "auto":
            try:
                thr_value = int(arg)
            except (TypeError, ValueError):
                bot.reply_to(self.message, "Неверный аргумент (должно быть целое число от 2 до "
                             + str(bot.get_chat_members_count(data.main_chat_id)) + " или \"auto\").")
                return

            if thr_value > bot.get_chat_members_count(data.main_chat_id):
                bot.reply_to(self.message, "Количество голосов не может быть больше количества участников в чате.")
                return
            elif thr_value < 2 and not data.debug:
                bot.reply_to(self.message, "Количество голосов не может быть меньше 2")
                return
            elif thr_value < 1:
                bot.reply_to(self.message, "Количество голосов не может быть меньше 1 (в дебаг-режиме)")
                return
        else:
            thr_value = 0

        second_arg = extract_arg(self.msg_txt, 2)
        if second_arg is None:
            self.main(thr_value)
        elif second_arg == "ban":
            self.ban(thr_value)
        elif second_arg == "min":
            self.min(thr_value)
        else:
            bot.reply_to(self.message, "Неизвестный второй аргумент, см. /threshold help")

    def main(self, thr_value):
        self.pre_vote(thr_value, "threshold")

    def ban(self, thr_value):
        self.pre_vote(thr_value, "threshold_ban")

    def min(self, thr_value):
        if not data.debug:
            self.current_timer = 86400
        self.pre_vote(thr_value, "threshold_min")

    def pre_vote(self, thr_value, vote_type):

        self.unique_id = vote_type

        if self.is_voting_exist():
            return

        if vote_type == "threshold_min":
            vote_type_text = "минимального порога голосов"
        elif vote_type == "threshold_ban":
            vote_type_text = "порога голосов бан-голосований"
        else:
            vote_type_text = "порога голосов стандартных голосований"

        if 0 < thr_value < data.thresholds_get(minimum=True) and vote_type != "threshold_min":
            bot.reply_to(self.message, f"Количество голосов не может быть ниже текущего "
                                       f"минимального порога {data.thresholds_get(minimum=True)}")
            return

        if thr_value == data.thresholds_get(vote_type == "threshold_ban", vote_type == "threshold_min"):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if data.is_thresholds_auto(vote_type == "threshold_ban", vote_type == "threshold_min") and thr_value == 0:
            bot.reply_to(self.message, "Значения порога уже вычисляются автоматически!")
            return

        warn = ''
        if vote_type == "threshold_min":
            warn = ("\n<b>Внимание! Результаты голосования за минимальный порог принимаются, "
                    "даже если голосование набрало количество голосов ниже текущего минимального порога!\n"
                    "Время завершения голосования за минимальный порог - 24 часа!</b>")

        if thr_value != 0:
            self.vote_text = (f"Тема голосования: установка {vote_type_text} на значение {thr_value}.\n"
                              f"Инициатор голосования: {username_parser(self.message, True)}." + warn)
        else:
            self.vote_text = (f"Тема голосования: установка {vote_type_text} на автоматически выставляемое значение.\n"
                              f"Инициатор голосования: {username_parser(self.message, True)}." + warn)
        self.vote_args = [thr_value, self.unique_id]
        self.poll_maker()


class Timer(PreVote):
    help_text = "Использовать как /timer [время] [ban или без аргумента],\n" \
                "или как /timer [время|0 (без кулдауна)|off|disable] random.\n" \
                "Подробнее о парсинге времени - см. команду /help."

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message, not_in_private_dialog=True):
            return True
        return None

    def help(self):
        if self.message.chat.id != data.main_chat_id:
            bot.reply_to(self.message, "Использовать как  /timer [время|0 (без кулдауна)|off|disable] random.\n"
                                       "Подробнее о парсинге времени - см. команду /help.,", parse_mode="html")
        elif self.help_access_check():
            bot.reply_to(self.message, self.help_text, parse_mode="html")

    def direct_fn(self):
        timer_text = ""
        if self.message.chat.id == data.main_chat_id:
            timer_text = formatted_timer(data.global_timer) + " для обычного голосования.\n" \
                         + formatted_timer(data.global_timer_ban) + " для голосования за бан.\n"
        abuse_random_time = sqlWorker.abuse_random(self.message.chat.id)
        if abuse_random_time == -1:
            timer_random_text = "Команда /random отключена."
        elif abuse_random_time == 0:
            timer_random_text = "Кулдаун команды /random отключён."
        else:
            timer_random_text = f"{formatted_timer(abuse_random_time)} - кулдаун команды /random."
        bot.reply_to(self.message, "Текущие пороги таймера:\n" + timer_text + timer_random_text)

    def arg_fn(self, arg):
        if extract_arg(self.msg_txt, 2) != "random":
            if command_forbidden(self.message, text="Команду с данным аргументом невозможно "
                                                          "запустить не в основном чате."):
                return
        timer_arg = time_parser(arg)
        second_arg = extract_arg(self.msg_txt, 2)
        if second_arg is None or second_arg == "ban":
            self.main_and_ban(timer_arg, second_arg)
        elif second_arg == "random":
            self.random(timer_arg)
        else:
            bot.reply_to(self.message, "Неверный второй аргумент (должен быть ban, random или пустой).")
            return

    def main_and_ban(self, timer_arg, second_arg):
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 5 секунд до 1 суток).")
            return
        elif timer_arg < 5 or timer_arg > 86400:
            bot.reply_to(self.message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
            return
        if second_arg is None:
            self.main(timer_arg)
        else:
            self.ban(timer_arg)

    def main(self, timer_arg):
        self.unique_id = "timer"
        ban_text = "таймера стандартных голосований"
        if timer_arg == data.global_timer:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def ban(self, timer_arg):
        self.unique_id = "timer for ban votes"
        ban_text = "таймера бан-голосований"
        if timer_arg == data.global_timer_ban:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def random(self, timer_arg):
        self.unique_id = "timer for random cooldown"
        ban_text = "кулдауна команды /random"
        if extract_arg(self.msg_txt, 1) in ("off", "disable"):
            timer_arg = -1
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 0 секунд до 1 часа).")
            return
        elif timer_arg < -1 or timer_arg > 3600:
            bot.reply_to(self.message, "Количество времени не может быть меньше 0 секунд и больше 1 часа.")
            return
        elif timer_arg == sqlWorker.abuse_random(self.message.chat.id):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if self.message.chat.id != data.main_chat_id:
            user_status = bot.get_chat_member(self.message.chat.id, self.message.from_user.id).status
            if user_status not in ("creator", "administrator"):
                bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
                return
            sqlWorker.abuse_random(self.message.chat.id, timer_arg)
            if timer_arg == -1:
                bot.reply_to(self.message, "Команда /random отключена.")
            elif timer_arg == 0:
                bot.reply_to(self.message, "Кулдаун команды /random отключён.")
            else:
                bot.reply_to(self.message, "Установлен порог кулдауна команды "
                                           f"/random на значение {formatted_timer(timer_arg)}")
            return

        if timer_arg == 0:
            vote_text = (f"Тема голосования: отключение кулдауна команды /random."
                         f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        elif timer_arg == -1:
            vote_text = (f"Тема голосования: отключение команды /random."
                         f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        else:
            vote_text = ""
        self.pre_vote(timer_arg, ban_text, vote_text)

    def pre_vote(self, timer_arg, ban_text, vote_text=""):
        if self.is_voting_exist():
            return
        self.vote_text = vote_text or (f"Тема голосования: смена {ban_text} на значение "
                                       + formatted_timer(timer_arg) +
                                       f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [timer_arg, self.unique_id]
        self.poll_maker()


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


class PrivateMode(PreVote):
    help_text = "Существуют три режима приватности чата:\n" \
                "1. Использование вайтлиста и системы инвайтов. Участник, не найденный в вайтлисте или в " \
                "одном из союзных чатов, блокируется. Классическая схема, применяемая для приватных чатов.\n" \
                "2. Использование голосования при вступлении участника. При вступлении участника в чат " \
                "отправка от него сообщений ограничивается, выставляется голосование за возможность " \
                "его вступления в чат. По завершению голосования участник блокируется или ему позволяется " \
                "вступить в чат. Новая схема, созданная для публичных чатов.\n" \
                "3. Использование классической капчи при вступлении участника.\n" \
                "Если хостер бота выставил режим \"mixed\" в конфиге бота, можно сменить режим на другой " \
                "(команда /private 1/2/3), в противном случае хостер бота устанавливает режим работы " \
                "самостоятельно.\n<b>Текущие настройки чата:</b>" \
                "\nНастройки заблокированы хостером: {}" \
                "\nТекущий режим чата: {}{}"

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True
        return None

    def direct_fn(self):
        self.help()

    def help(self):
        if not self.help_access_check():
            return
        if data.binary_chat_mode == 0:
            chat_mode = "приватный"
        elif data.binary_chat_mode == 1:
            chat_mode = "публичный (с голосованием)"
        else:
            chat_mode = "публичный (с капчёй)"

        chat_mode_locked = "да" if data.chat_mode != "mixed" else "нет"
        shield_info = ""
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            shield_info = "\n<b>Внимание! Включён режим защиты чата (подробнее - /shield)</b>\n" \
                          f"До отключения осталось {formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text.format(chat_mode_locked, chat_mode, shield_info), parse_mode="html")

    def arg_fn(self, arg):
        if data.chat_mode != "mixed":
            bot.reply_to(self.message, "Хостер бота заблокировал возможность сменить режим работы бота.")
            return

        self.unique_id = "private mode"
        if self.is_voting_exist():
            return

        try:
            chosen_mode = int(arg) - 1
            if not 0 <= chosen_mode <= 2:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 1 до 3).")
            return

        if chosen_mode == data.binary_chat_mode:
            bot.reply_to(self.message, "Данный режим уже используется сейчас!")
            return

        chat_modes = ["приватный", "публичный (с голосованием)", "публичный (с капчёй)"]
        chat_mode = chat_modes[chosen_mode]

        self.vote_text = (f"Тема голосования: изменение режима приватности чата на {chat_mode}."
                          f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [chosen_mode, username_parser(self.message, True), chat_mode]
        self.poll_maker()


class Votes(PreVote):
    help_text = ("Используйте эту команду без аргументов, чтобы посмотреть список текущих голосований в данном чате.\n"
                 'Используйте аргумент "public", "private" или "hidden" для переключения режимов приватности '
                 'голосования.\nВсего существуют три режима:\n'
                 '1. Публичный (public) - всем участникам видно, кто и за какой вариант проголосовал (с помощью кнопки '
                 '"Список голосов"), а так же отображается счётчик голосов, оставленных за каждый из вариантов.\n'
                 '2. Приватный (private) - участникам виден только счётчик голосов для каждого варианта, но они могут '
                 'узнать, за какой вариант оставили голос, с помощью кнопки "Узнать мой голос".\n'
                 '3. Скрытый (hidden) - счётчик голосов для каждого варианта скрыт, но узнать свой голос с помощью '
                 'кнопки участники по прежнему могут. Используется для классического тайного голосования.\n\n'
                 '<b>В режимах "приватный" и "скрытый" ID проголосовавшего участника хэшируется в БД с использованием '
                 'значения <i>chat_instance</i>, уникального для каждого чата и экземпляра бота. Узнать данное '
                 'значение владелец бота может только при вмешательстве в работу экземпляра бота или установке плагина '
                 'с функцией просмотра chat_instance. В случае компрометации данного значения для восстановления '
                 'анонимности голосований настоятельно рекомендуется пересоздать бота для получения нового '
                 'chat_instance.\nТем не менее, в связи с техническими ограничениями владелец бота в любом случае '
                 'может посмотреть в БД <i>количество</i> голосов, отданных за определённый вариант .</b>\n\n'
                 'Вы можете использовать ключ --private, --public или --hidden (обязательно вторым словом) в '
                 'отправляемой боту команде, чтобы перезаписать глобальные настройки приватности для любого '
                 'создаваемого вами голосования. Например, команда <code>/title --public Тестовый чат</code> создаст '
                 'публичный опрос, даже если в чате глобально включен режим приватности голосований.\n'
                 '<b>Текущий статус приватности голосований</b>: {}')

    def pre_return(self) -> Optional[bool]:
        if (not bot_name_checker(self.message) or
                command_forbidden(self.message, not_in_private_dialog=True)):
            return True
        return None

    def help(self):
        status = {"public": "публичные", "private": "приватные", "hidden": "скрытые"}
        bot.reply_to(self.message, self.help_text.format(status[data.vote_privacy]), parse_mode="html")

    def direct_fn(self):
        records = sqlWorker.get_all_polls()
        poll_list = ""
        number = 1

        if bot.get_chat(self.message.chat.id).username is not None:
            format_chat_id = bot.get_chat(self.message.chat.id).username
        else:
            format_chat_id = f"c/{str(self.message.chat.id)[4:]}"

        for record in records:
            if record[3] != self.message.chat.id:
                continue
            record_chat_id = format_chat_id
            if self.message.chat.is_forum:
                thread_id = f'/{record[9]}' if record[9] else '/1'
                record_chat_id = format_chat_id + thread_id
            try:
                vote_type = poll_engine.post_vote_list[record[2]].description
            except KeyError:
                vote_type = "INVALID (не загружен плагин?)"
            poll_list = poll_list + f"{number}. https://t.me/{record_chat_id}/{record[1]}, " \
                                    f"тип - {vote_type}, " \
                                    f"до завершения – {formatted_timer(record[5] - int(time.time()))}\n"
            number = number + 1

        if poll_list == "":
            poll_list = "В этом чате нет активных голосований!"
        else:
            poll_list = "Список активных голосований:\n" + poll_list

        bot.reply_to(self.message, poll_list)

    def set_args(self) -> dict:
        return {"private": self.vote_privacy_private,
                "public": self.vote_privacy_public,
                "hidden": self.vote_privacy_hidden}

    def vote_privacy_private(self):
        if data.vote_privacy == 'private':
            bot.reply_to(self.message, "Голосования уже являются приватными!")
            return
        self.vote_privacy('private')

    def vote_privacy_public(self):
        if data.vote_privacy == 'public':
            bot.reply_to(self.message, "Голосования уже являются публичными!")
            return
        self.vote_privacy('public')

    def vote_privacy_hidden(self):
        if data.vote_privacy == 'hidden':
            bot.reply_to(self.message, "Голосования уже являются скрытыми!")
            return
        self.vote_privacy('hidden')

    def vote_privacy(self, vote_privacy_mode):
        if self.is_voting_exist():
            return
        self.vote_type = "vote_privacy"
        self.unique_id = self.vote_type
        vote_privacy_text = {'private': 'приватный', 'public': 'публичный', 'hidden': 'скрытый'}
        self.vote_text = (f"Тема голосования: глобальное переключение голосований в "
                          f"{vote_privacy_text[vote_privacy_mode]} режим.\n"
                          f"<b>Режим приватности уже запущенных голосований не будет переключен.</b>\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [vote_privacy_mode, username_parser(self.message)]
        self.poll_maker()


class Shield(PreVote):
    vote_type = "shield"
    unique_id = vote_type
    help_text = 'Эта команда включает режим защиты чата - Раскрытый Зонтик. В этом режиме бот блокирует входящих ' \
                'пользователей при попытке входа из союзного чата и напрямую, а так же ботов при попытке их ' \
                'добавить. В режиме чата "приватный" войти в чат всё ещё будет возможно по вайтлисту.\n' \
                'Аргумент "force", доступный только администраторам, позволит включить режим защиты чата на срок от ' \
                '1 до 24 часов, по умолчанию на 12 часов. Аргумент "enable" и "disable" позволит голосованием ' \
                'включить (обновить таймер) и отключить режим защиты чата на срок от 1 часа до 30 дней.\n' \
                'В режиме защиты бот удаляет сообщение о входе пользователя, не оставляя следов при флуд-атаке.\n'

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True
        return None

    def help(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            status = "<b>Текущий статус защиты</b>: отключена."
        else:
            status = f"<b>Текущий статус защиты</b>: включена.\n<b>До отключения осталось:</b> " \
                     f"{formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text + status, parse_mode="html")

    def direct_fn(self):
        self.help()

    def set_args(self) -> dict:
        return {"force": self.force, "enable": self.enable, "disable": self.disable}

    def force(self):
        if not bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("creator", "administrator"):
            bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
            return
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            bot.reply_to(self.message, "Защита уже включена! До отключения осталось "
                                       f"{formatted_timer(shield_timer - int(time.time()))}")
            return
        timer = time_parser(extract_arg(self.msg_txt, 2))
        if timer is None:
            timer = 43200
        if not 3600 <= timer <= 86400:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 до 24 часов!")
            return
        sqlWorker.params("shield", rewrite_value=int(time.time()) + timer)
        bot.reply_to(self.message, f"Защита чата успешно включена на {formatted_timer(timer)} "
                                   "Теперь добавление новых участников временно невозможно!")

    def enable(self):
        timer = extract_arg(self.msg_txt, 2)
        if not timer:
            bot.reply_to(self.message, "Требуется указать третьим аргументом значение таймера защиты "
                                       "(от 1 часа до 30 дней)")
            return
        timer = time_parser(timer)
        if timer is None:
            bot.reply_to(self.message, "Не удалось распарсить аргумент таймера.")
            return
        if not 3600 <= timer <= 2592000:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 часа до 30 дней!")
            return
        self.create_vote("включение/обновление таймера", timer)

    def disable(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            bot.reply_to(self.message, "Защита чата уже отключена!")
            return
        self.create_vote("отключение", 0)

    def create_vote(self, vote_type, timer):
        if self.is_voting_exist():
            return
        timer_text = "." if timer == 0 else f" на {formatted_timer(timer)}"
        self.vote_text = (f"Тема голосования: {vote_type} режима защиты чата от атак{timer_text}\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(vote_args=[timer, username_parser(self.message, True)])


class Marmalade(PreVote):
    vote_type = "marmalade"
    unique_id = vote_type
    help_text = ("Marmalade - механизм защиты чата от проникновения новых пользователей через союзные чаты.\n"
                 "Когда кто-то заходит в союзный чат, бот запоминает его, если данного человека нет в основном чате. "
                 "Если данный человек попробует зайти в основной чат раньше, чем через 18 часов после этого, ему "
                 "потребуется пройти стандартную процедуру голосования для вступления (внутри чата) или капчу, в "
                 "зависимости от настроек приватности чата. Если прошло более 18 часов или бот не зафиксировал "
                 "вступление в союзный чат, то человек может войти без каких-либо проверок. Запись в БД актуальна в "
                 "течении недели. Если по истечении этого времени человек перезашёл в союзный чат, то запись "
                 "обновляется. Вы можете включить и выключить Marmalade с помощью голосования, однако настоятельно "
                 "рекомендуется оставить его включённым (по умолчанию).\n")

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True
        return None

    def help(self):
        marmalade = sqlWorker.params("marmalade", default_return=True)
        marmalade_text = "включена" if marmalade else "отключена"
        status = f"<b>Текущий статус защиты</b>: {marmalade_text}."
        bot.reply_to(self.message, self.help_text + status, parse_mode="html")

    def direct_fn(self):
        self.help()

    def set_args(self) -> dict:
        return {"enable": self.enable, "disable": self.disable}

    def enable(self):
        if sqlWorker.params("marmalade", default_return=True):
            bot.reply_to(self.message, "Защита чата Marmalade уже включена!")
            return
        self.create_vote(True)

    def disable(self):
        if not sqlWorker.params("marmalade", default_return=True):
            bot.reply_to(self.message, "Защита чата Marmalade уже отключена!")
            return
        self.create_vote(False)

    def create_vote(self, marmalade_bool):
        if self.is_voting_exist():
            return
        marmalade_text = "включение" if marmalade_bool else "отключение"
        self.vote_text = (f"Тема голосования: {marmalade_text} механизма защиты чата Marmalade\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(vote_args=[marmalade_bool, username_parser(self.message, True)])
