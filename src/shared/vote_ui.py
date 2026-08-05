import hashlib
import logging
import time

import telebot
from telebot import types

from teleboss.shared.parsers import formatted_timer
from teleboss.shared.runtime import data, bot, sqlWorker


def make_keyboard(buttons_scheme, hidden):
    row_width = 2
    formatted_buttons = []
    for button in buttons_scheme:
        if "vote!" in button["button_type"]:
            text = button["name"]
            if not hidden:
                text += f' - {len(button["user_list"])}'
            formatted_buttons.append(types.InlineKeyboardButton(text=text, callback_data=button["button_type"]))
        elif button["button_type"] == "row_width":
            row_width = button["row_width"]  # Феерически убогий костыль, но мне нравится))))
        else:
            formatted_buttons.append(types.InlineKeyboardButton(
                text=button["name"], callback_data=button["button_type"]))
    keyboard = types.InlineKeyboardMarkup(row_width=row_width)
    keyboard.add(*formatted_buttons)
    return keyboard


def vote_make(text, message, buttons_scheme, add_user, direct, hidden):
    if add_user:
        vote_message = bot.send_message(data.main_chat_id, text, reply_markup=make_keyboard(
            buttons_scheme, hidden), parse_mode="html", message_thread_id=data.thread_id)
    elif direct:
        vote_message = bot.send_message(message.chat.id, text, reply_markup=make_keyboard(
            buttons_scheme, hidden), parse_mode="html", message_thread_id=message.message_thread_id)
    else:
        vote_message = bot.reply_to(message, text, reply_markup=make_keyboard(
            buttons_scheme, hidden), parse_mode="html")

    return vote_message


def get_hash(user_id, chat_instance, button_data) -> str:
    for button in button_data:
        if button["button_type"] == "user_votes":
            return user_id

    return hashlib.pbkdf2_hmac('sha256', str(user_id).encode('utf-8'),
                               chat_instance.encode('utf-8'), 100000, 16).hex()


def button_anonymous_checker(user_id, chat_id):
    try:
        for admin in bot.get_chat_administrators(chat_id):
            if admin.user.id == user_id:
                if admin.is_anonymous:
                    return True
        return False
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking user with ID {user_id} for being an anonymous administrator.\n{e}")
        return None


def make_mailing(vote_type, message_vote_id, current_timer):
    mailing_list = sqlWorker.mailing_get_all()
    if not mailing_list:
        return
    if bot.get_chat(data.main_chat_id).username is not None:
        format_chat_id = bot.get_chat(data.main_chat_id).username
    else:
        format_chat_id = "c/" + str(data.main_chat_id)[4:]
    for subscriber_index in range(len(mailing_list)):
        if not subscriber_index % 10 and subscriber_index:
            time.sleep(10)  # Protection against too many requests
        subscriber = mailing_list[subscriber_index][0]
        if bot.get_chat_member(data.main_chat_id, subscriber).status in ("left", "kicked"):
            sqlWorker.mailing(subscriber, remove=True)
            logging.warning(f"The user with ID {subscriber} is no longer a member of "
                            f"the chat and has been excluded from mailing list.")
            continue
        try:
            bot.send_message(subscriber,
                             f"<b>Было запущено новое голосование!</b>\n\nТип голосования: {vote_type}, "
                             f"длительность: {formatted_timer(current_timer)}\n"
                             f"Ссылка на голосование: https://t.me/{format_chat_id}/{message_vote_id}",
                             parse_mode='html')
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Errors sending mailing to user with ID {subscriber}, "
                          f"he will be excluded from the mailing list.\n{e}")
            sqlWorker.mailing(subscriber, remove=True)
