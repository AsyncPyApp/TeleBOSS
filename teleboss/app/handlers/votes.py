"""Callback handlers for vote, cancel, close, and vote-info buttons."""

import json
import os
import time

import telebot

from teleboss.shared.parsers import html_fix, username_parser_chat_member
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.shared.storage.sql_worker import ApplyVoteStatus
from teleboss.shared.vote_ui import get_hash, make_keyboard
from teleboss.voting.engine import poll_engine


class _VoteSoftReject(Exception):
    """User-facing vote rejection raised inside an ``apply_vote`` mutator."""


def call_msg_chk(call_msg):
    """Load the open poll for a callback's displayed message.

    Args:
        call_msg: Telegram callback query whose message identifies the poll.

    Returns:
        Zero or one open poll row for ``(chat_id, message_id)``.
    """
    records = sqlWorker.get_open_poll(
        call_msg.message.chat.id, call_msg.message.id
    )
    if not records:
        bot.edit_message_text(
            html_fix(call_msg.message.text)
            + "\n\n<b>Голосование не найдено в БД и закрыто.</b>",
            call_msg.message.chat.id,
            call_msg.message.id,
            parse_mode="html",
        )
        try:
            bot.unpin_chat_message(call_msg.message.chat.id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            pass

    return records


@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_vote(call_msg):
    """Cancel an open poll when the cancel-button author clicks cancel.

    Args:
        call_msg: Telegram callback query with ``data == \"cancel\"``.
    """
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "cancel":
            if button["user_id"] != call_msg.from_user.id:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text='Вы не можете отменить чужое голосование!', show_alert=True)
                return

    poll_engine.vote_abuse.clear()
    # Author cancel removes an open row; no completed-only delete API applies.
    sqlWorker.rem_rec(poll[0][0])
    try:
        os.remove(data.path + poll[0][0])
    except IOError:
        pass
    bot.edit_message_text(html_fix(call_msg.message.text)
                          + "\n\n<b>Голосование было отменено автором голосования.</b>",
                          call_msg.message.chat.id, call_msg.message.id, parse_mode="html")
    bot.reply_to(call_msg.message, "Голосование было отменено.")

    try:
        bot.unpin_chat_message(call_msg.message.chat.id, call_msg.message.id)
    except telebot.apihelper.ApiTelegramException:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "close")
def close_vote(call_msg):
    """Close an open poll early when the close-button author confirms.

    Args:
        call_msg: Telegram callback query with ``data == \"close\"``.
    """
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "close":
            if button["user_id"] != call_msg.from_user.id:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text='Вы не можете закрыть чужой опрос!', show_alert=True)
                return

    poll_engine.vote_abuse.clear()
    poll_engine.vote_result(poll[0][0], call_msg.message.id)


@bot.callback_query_handler(func=lambda call: call.data == "my_vote")
def my_vote(call_msg):
    """Show the caller's current choice in the open poll, if any.

    Args:
        call_msg: Telegram callback query with ``data == \"my_vote\"``.
    """
    if data.main_chat_id == -1:  # Проверка на init mode
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Бот работает в режиме инициализации!', show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Данный опрос не найден или закрыт.', show_alert=True)
        return

    button_data = json.loads(poll[0][4])
    user_hash = get_hash(call_msg.from_user.id, call_msg.chat_instance, button_data)

    for button in button_data:
        if "vote!" in button["button_type"]:
            if user_hash in button["user_list"]:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text=f'Вы голосовали за вариант "{button["name"]}".', show_alert=True)
                return
    bot.answer_callback_query(callback_query_id=call_msg.id, text='Вы не голосовали в данном опросе!', show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "user_votes")
def user_votes(call_msg):
    """List voters per option for an open poll (alert or private message).

    Args:
        call_msg: Telegram callback query with ``data == \"user_votes\"``.
    """
    if data.main_chat_id == -1:  # Проверка на init mode
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Бот работает в режиме инициализации!', show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Данный опрос не найден или закрыт.', show_alert=True)
        return

    button_data = json.loads(poll[0][4])

    answer_text = "Список проголосовавших:\n"
    for button in button_data:
        if "vote!" in button["button_type"]:
            answer_user_list = []
            for user_id in button["user_list"]:
                try:
                    username = username_parser_chat_member(bot.get_chat_member(call_msg.message.chat.id, user_id),
                                                                 html=False, need_username=False)
                    if username == "":
                        continue
                    answer_user_list.append(username)
                except telebot.apihelper.ApiTelegramException:
                    continue
            if answer_user_list:
                answer_user_list = ", ".join(answer_user_list) + f" (всего {len(answer_user_list)})"
            else:
                answer_user_list = "нет голосов"
            button_name = button["name"]
            answer_text += f'"{button_name}" - {answer_user_list}\n'

    if len(answer_text) < 200:
        bot.answer_callback_query(callback_query_id=call_msg.id, text=answer_text, show_alert=True)
    else:
        try:
            bot.send_message(call_msg.from_user.id, answer_text)
            answer_text = "Cписок голосующих слишком длинный для вывода всплывающим окном. Отправил вам сообщение в л/с"
        except telebot.apihelper.ApiTelegramException:
            answer_text = ("Я не смог отправить сообщение вам в л/с и список голосующих слишком длинный для вывода "
                           "всплывающим окном. Недостаточно прав или нет личного диалога?")
        bot.answer_callback_query(callback_query_id=call_msg.id, text=answer_text, show_alert=True)


# Register op! before vote! (Telegram handler registration order).
from teleboss.app.handlers import op as _op  # noqa: E402, F401


@bot.callback_query_handler(func=lambda call: "vote!" in call.data)
def vote_button(call_msg):
    """Apply a ``vote!`` choice atomically, then update markup or close.

    Args:
        call_msg: Telegram callback query whose ``data`` contains ``vote!``.
    """
    if data.main_chat_id == -1:  # Проверка на init mode
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Бот работает в режиме инициализации!', show_alert=True)
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    captcha_unique_id = f"{call_msg.from_user.id}_new_usr"
    captcha_poll = sqlWorker.get_poll_by_unique_id(captcha_unique_id)
    if captcha_poll:
        if captcha_poll[0][5] <= int(time.time()):
            sqlWorker.rem_rec(captcha_poll[0][0])
        else:
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text="Вы ещё не прошли капчу и не можете голосовать!", show_alert=True)
            return

    if sqlWorker.captcha(call_msg.message.message_id, user_id=call_msg.from_user.id):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы ещё не прошли капчу и не можете голосовать!", show_alert=True)
        return

    if poll_engine.get_abuse_timer(call_msg):  # Voting click check
        return

    chat_id = call_msg.message.chat.id
    message_id = call_msg.message.id
    current_choice = call_msg.data.split("_")[1]
    soft_alert: list[str] = []
    vote_ctx: dict = {
        "last_choice": None,
        "button_data": None,
    }

    def mutator(poll_row) -> str:
        """Validate vote mode rules and return updated buttons JSON.

        Args:
            poll_row: Open poll row locked by ``apply_vote``.

        Returns:
            Serialized buttons JSON after applying the vote rules.

        Raises:
            _VoteSoftReject: When the click is rejected without mutation.
        """
        button_data = json.loads(poll_row[4])
        user_hash = get_hash(
            call_msg.from_user.id, call_msg.chat_instance, button_data
        )

        last_choice = None
        for button in button_data:
            if "vote!" in button["button_type"]:
                if user_hash in button["user_list"]:
                    last_choice = button["name"]
                    break

        if data.vote_mode == 1:
            if last_choice is not None:
                soft_alert.append(
                    f'Вы уже голосовали за вариант "{last_choice}". '
                    f"Смена голоса запрещена."
                )
                raise _VoteSoftReject()
            for button in button_data:
                if "vote!" in button["button_type"] and button["name"] == current_choice:
                    button["user_list"].append(user_hash)
                    break
        elif data.vote_mode == 2:
            if last_choice == current_choice:
                soft_alert.append(
                    f'Вы уже голосовали за вариант "{last_choice}". '
                    f"Отмена голоса запрещена."
                )
                raise _VoteSoftReject()
            for button in button_data:
                if "vote!" in button["button_type"] and button["name"] == current_choice:
                    button["user_list"].append(user_hash)
                if "vote!" in button["button_type"] and button["name"] == last_choice:
                    button["user_list"].remove(user_hash)
        elif data.vote_mode == 3:
            if last_choice == current_choice:
                for button in button_data:
                    if "vote!" in button["button_type"] and button["name"] == current_choice:
                        button["user_list"].remove(user_hash)
            else:
                for button in button_data:
                    if "vote!" in button["button_type"] and button["name"] == current_choice:
                        button["user_list"].append(user_hash)
                    if "vote!" in button["button_type"] and button["name"] == last_choice:
                        button["user_list"].remove(user_hash)

        vote_ctx["last_choice"] = last_choice
        vote_ctx["button_data"] = button_data
        return json.dumps(button_data)

    result = sqlWorker.apply_vote(chat_id, message_id, mutator)

    if soft_alert:
        bot.answer_callback_query(
            callback_query_id=call_msg.id, text=soft_alert[0], show_alert=True
        )
        return

    if result.status in (ApplyVoteStatus.NOT_FOUND, ApplyVoteStatus.NOT_OPEN):
        bot.edit_message_text(
            html_fix(call_msg.message.text)
            + "\n\n<b>Голосование не найдено в БД и закрыто.</b>",
            call_msg.message.chat.id,
            call_msg.message.id,
            parse_mode="html",
        )
        try:
            bot.unpin_chat_message(call_msg.message.chat.id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            pass
        bot.answer_callback_query(
            callback_query_id=call_msg.id,
            text="Данный опрос не найден или закрыт.",
            show_alert=True,
        )
        return

    if result.status != ApplyVoteStatus.OK or result.poll is None:
        bot.answer_callback_query(
            callback_query_id=call_msg.id,
            text="Не удалось сохранить голос. Попробуйте ещё раз.",
            show_alert=True,
        )
        return

    poll = result.poll
    button_data = vote_ctx["button_data"]
    last_choice = vote_ctx["last_choice"]
    if button_data is None:
        button_data = json.loads(poll[4])

    hidden = bool(poll[8])
    if hidden:
        if last_choice == current_choice:
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Вы сняли голос с варианта "{current_choice}"')
        else:
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Вы проголосовали за вариант "{current_choice}"')

    # Checking that there are enough votes to close the vote
    voting_completed = False
    poll_sum = 0
    for button in button_data:
        if "vote!" in button["button_type"]:
            if poll[2] == "custom poll":
                poll_sum += len(button["user_list"])
            elif len(button["user_list"]) >= poll[7]:
                voting_completed = True
                break

    if poll_sum >= bot.get_chat_member_count(call_msg.message.chat.id) - 1:  # The bot itself will not be counted
        voting_completed = True

    if voting_completed or poll[5] <= int(time.time()):
        poll_engine.vote_abuse.clear()
        poll_engine.vote_result(poll[0], call_msg.message.id)
        return

    # Making changes to the message only after successful persistence
    if not hidden:
        bot.edit_message_reply_markup(
            call_msg.message.chat.id,
            message_id=call_msg.message.id,
            reply_markup=make_keyboard(button_data, False),
        )
    poll_engine.vote_abuse.update(
        {str(call_msg.message.id) + "." + str(call_msg.from_user.id): int(time.time())}
    )
