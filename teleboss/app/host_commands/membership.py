"""Membership host command handlers."""

import json
import logging

import telebot

from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import topic_reply_fix
from teleboss.shared.runtime import bot, sqlWorker


class MembershipMixin:
    """Mixin providing membership-related host commands."""

    @staticmethod
    def add_answer(message):
        """Reply to an invite-poll applicant using the host ``/answer`` command.

        Resolves the replied poll by the command chat and replied message id
        so same message ids in other chats cannot cross-resolve.

        Args:
            message: Host command message that replies to an invite poll.
        """
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if topic_reply_fix(message.reply_to_message) is None:
            bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на заявку на вступление")
            return

        poll = sqlWorker.get_open_poll(
            message.chat.id, message.reply_to_message.id
        )
        if poll:
            if poll[0][2] != "invite":
                bot.reply_to(message, "Данное голосование не является голосованием о вступлении.")
                return
        else:
            bot.reply_to(message, "Заявка на вступление не найдена или закрыта.")
            return

        try:
            msg_from_usr = message.text.split(None, 1)[1]
        except IndexError:
            bot.reply_to(message, "Ответ не может быть пустым.")
            return

        data_list = json.loads(poll[0][6])

        try:
            bot.send_message(data_list[0], "Сообщение на вашу заявку от участника чата - \"" + msg_from_usr + "\"")
            bot.reply_to(message, "Сообщение пользователю отправлено успешно.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error sending message to applicant for membership!\n{e}')
            bot.reply_to(message, "Ошибка отправки сообщению пользователю.")
