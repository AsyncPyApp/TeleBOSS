import json
import logging
import threading
import time
import traceback
from typing import Optional

import telebot

from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    reply_msg_target as reply_msg_target_fn,
    username_parser_chat_member,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.shared.vote_ui import make_mailing, vote_make
from teleboss.voting.engine import poll_engine
from teleboss.voting.exceptions import InternalBotException, SilentException


class PreVote:
    args = {}  # Dictionary of possible command arguments
    vote_text = ""
    user_id = ""
    add_user = False
    silent = False
    unique_id = ""
    vote_type = ""
    vote_args = []
    help_text = "У этой команды нет справки!"
    reply_user_id = ""
    reply_username = ""
    reply_is_bot = False
    direct = False
    msg_txt = ""

    def __init__(self, message):
        if not bot_name_checker(message):
            return
        self.message = message
        self.user_id = message.from_user.id
        self.msg_txt = message.text
        self.privacy = data.vote_privacy
        first_arg = extract_arg(self.msg_txt, 1)
        if first_arg == "help":
            self.help()
            return
        elif first_arg in ("--private", "--public", "--hidden"):
            self.privacy = first_arg[2::]
            self.msg_txt = self.msg_txt.replace(f" {first_arg}", "", 1)
            first_arg = extract_arg(self.msg_txt, 1)
        self.current_timer, self.current_votes = self.timer_votes_init()
        if self.pre_return():
            return
        self.args = self.set_args()
        if first_arg is None:
            self.direct_fn()
        else:
            self.arg_fn(first_arg)

    def set_args(self) -> dict:
        """return dictionary of class functions"""
        return {}

    def pre_return(self) -> Optional[bool]:
        """Checking for conditions that will cause the command to be canceled prematurely"""
        return False

    def pre_return_command_forbidden(self) -> Optional[bool]:
        """Cancel early when ``command_forbidden(self.message)`` is true.

        Returns:
            True when the command must abort; otherwise None.
        """
        if command_forbidden(self.message):
            return True
        return None

    @staticmethod
    def timer_votes_init():
        """timer, votes"""
        return data.global_timer, data.thresholds_get()

    @staticmethod
    def timer_votes_init_ban():
        """Ban-timer defaults: ``global_timer_ban`` and ban thresholds.

        Returns:
            Tuple of (timer seconds, vote threshold).
        """
        return data.global_timer_ban, data.thresholds_get(True)

    def direct_fn(self):  # If the command was run without arguments
        bot.reply_to(self.message, "Эту команду нельзя запустить без аргументов!")

    def arg_fn(self, arg):  # If the command was run with arguments
        if self.args:
            try:
                self.args[arg]()  # Runs a function from a dictionary by default
            except KeyError:
                bot.reply_to(self.message, "Данного аргумента команды не существует!")
        else:
            bot.reply_to(self.message, "У этой команды нет аргументов!")

    def help(self):
        if self.help_access_check():
            bot.reply_to(self.message, self.help_text, parse_mode="html")

    def help_access_check(self):
        if self.message.chat.id != data.main_chat_id:
            if self.message.chat.id == self.message.from_user.id:
                if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                    bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                    return False
            else:
                bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                return False
        return True

    def is_voting_exist(self):
        """Return True when an active logical poll for ``unique_id`` exists.

        Expired open rows are removed so a new vote may start. Lookup is by
        ``unique_id`` only (no message-only reconstruction).

        Returns:
            True when a non-expired poll still blocks a duplicate start.
        """
        poll = sqlWorker.get_poll_by_unique_id(self.unique_id)
        if poll:
            if poll[0][5] <= int(time.time()):
                sqlWorker.rem_rec(poll[0][0])
                return False
            bot.reply_to(self.message, "Голосование о данном вопросе уже идёт.")
            return True
        return False

    def get_votes_text(self):
        return f"{self.vote_text}\nГолосование будет закрыто через {formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def poll_maker(self, vote_args: list = None, unique_id: str = None, vote_text: str = None, vote_type: str = None,
                   current_timer: int = None, current_votes: int = None,
                   user_id: int = None, add_user=False, silent=False, direct=False):
        self.vote_args = vote_args or self.vote_args
        self.unique_id = unique_id or self.unique_id
        self.vote_text = vote_text or self.vote_text
        self.vote_type = vote_type or self.vote_type
        self.current_timer = current_timer or self.current_timer
        self.current_votes = current_votes or self.current_votes
        self.user_id = user_id or self.user_id
        self.add_user = add_user
        self.silent = silent
        self.direct = direct
        self.__poll_constructor()

    def __poll_constructor(self):
        vote_text = self.get_votes_text()
        buttons_scheme = self.get_buttons_scheme()
        hidden = True if self.privacy == "hidden" else False
        message_vote = vote_make(vote_text, self.message, buttons_scheme, self.add_user, self.direct, hidden)
        topic_id = None
        if message_vote.message_thread_id and self.message.chat.is_forum:
            topic_id = message_vote.message_thread_id

        sqlWorker.add_poll(self.unique_id, message_vote.id, self.vote_type, message_vote.chat.id,
                           json.dumps(buttons_scheme), int(time.time()) + self.current_timer,
                           json.dumps(self.vote_args), self.current_votes, hidden, topic_id)
        if not self.silent:
            threading.Thread(target=make_mailing, daemon=True,
                             args=(poll_engine.post_vote_list[self.vote_type].description, message_vote.id,
                                   self.current_timer)).start()
            try:
                bot.pin_chat_message(message_vote.chat.id, message_vote.message_id, disable_notification=True)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f"I can't pin message in chat {message_vote.chat.id}!\n{e}")
        threading.Thread(target=poll_engine.vote_timer, daemon=True,
                         args=(self.current_timer, self.unique_id, message_vote.message_id)).start()

    def get_buttons_scheme(self):
        button_scheme = [{"button_type": f"vote!_{i}", "name": i, "user_list": []} for i in ("Да", "Нет")]
        if self.privacy == 'public':
            button_scheme.append({"button_type": "user_votes",
                                  "name": "Список голосов"})
        else:
            button_scheme.append({"button_type": "my_vote",
                                  "name": "Узнать мой голос"})
        if not (data.bot_id == self.user_id or self.user_id == data.ANONYMOUS_ID):
            button_scheme.append({"button_type": "cancel",
                                  "name": "Отмена голосования",
                                  "user_id": self.user_id})
        return button_scheme

    def reply_msg_target(self):
        self.reply_user_id, self.reply_username, self.reply_is_bot = \
            reply_msg_target_fn(self.message.reply_to_message)


class PostVote:

    accept_text = ""
    decline_text = ""
    _description = ""  # Описание голосования
    votes_counter = ""
    is_accept = False
    records = []
    data_list = []
    message_vote_id = None
    message_vote_chat_id = None

    def post_vote(self, records) -> bool | None:
        """Apply post-vote effects for a claimed poll row.

        Outcome protocol for the completion engine:
        ``True`` means success; ``False`` means controlled failure (row retained
        as ``failed``); legacy overrides may return ``None``, which the engine
        treats as success only when no exception was raised.

        Args:
            records: Poll row tuple (offsets 0–9 used by handlers).

        Returns:
            ``True`` on success, ``False`` on caught controlled failure.
        """
        self.data_list = json.loads(records[6])
        self.message_vote_id = records[1]
        self.message_vote_chat_id = records[3]
        button_data = json.loads(records[4])
        counters_yes = 0
        counters_yes_text = counters_yes
        counters_no = 0
        counters_no_text = counters_no
        votes_private = True
        for button in button_data:
            if button["button_type"] == "user_votes":
                votes_private = False
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                    if votes_private:
                        counters_yes_text = counters_yes
                    else:
                        counters_yes_text = self.get_voted_usernames(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])
                    if votes_private:
                        counters_no_text = counters_no
                    else:
                        counters_no_text = self.get_voted_usernames(button["user_list"])
        self.votes_counter = f"\nЗа: {counters_yes_text}\nПротив: {counters_no_text}"
        if counters_yes > counters_no and counters_yes + counters_no >= data.thresholds_get(minimum=True):
            self.is_accept = True
        elif counters_yes + counters_no >= data.thresholds_get(minimum=True):
            self.is_accept = False
        else:
            self.is_accept = False
            self.votes_counter = f"\nНедостаточно голосов (требуется как минимум {data.thresholds_get(minimum=True)})"
        self.records = records
        self.post_vote_child()
        try:
            if self.is_accept:
                self.accept()
            else:
                self.decline()
            self.final_hook(False)
            return True
        except SilentException:
            # Control-flow success: accept already finished UX; skip final_hook.
            return True
        except (telebot.apihelper.ApiTelegramException, InternalBotException) as e:
            logging.error(f'Error in poll {records[0]} with type "{records[2]}", '
                          f'chat ID {records[3]} and message ID {records[1]}\n{e}')
            self.final_hook(True)
            return False
        except Exception as e:
            logging.error(f'Unknown error in poll "{records[0]}" with type "{records[2]}", '
                          f'chat ID "{records[3]}" and message ID "{records[1]}"\n{e}')
            logging.error(traceback.format_exc())
            self.final_hook(True)
            return False

    def get_voted_usernames(self, user_list):
        usernames = []
        for user_id in user_list:
            try:
                username = username_parser_chat_member(
                    bot.get_chat_member(self.message_vote_chat_id, user_id), html=True)
                if username == "":
                    continue
                usernames.append(username)
            except telebot.apihelper.ApiTelegramException:
                continue
        return "нет голосов" if not usernames else ", ".join(usernames) + f" (всего {len(usernames)})"

    def post_vote_child(self):
        return

    def accept(self):
        return

    def decline(self):
        return

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
            else:
                bot.send_message(self.message_vote_chat_id, "Голосование завершено!",
                                 reply_to_message_id=self.message_vote_id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    @property
    def description(self):
        return self._description

    def change_rate(self, change):
        if all([not bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).user.is_bot,
                not bot.get_chat_member(self.message_vote_chat_id, self.data_list[0]).status == "restricted",
                data.rate]):
            sqlWorker.update_rate(self.data_list[0], change)
            return True
        return False
