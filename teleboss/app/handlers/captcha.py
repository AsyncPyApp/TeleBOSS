import telebot

import utils
from utils import data, bot, sqlWorker


@bot.callback_query_handler(func=lambda call: "captcha" in call.data)
def captcha_buttons(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    data_list = sqlWorker.captcha(call_msg.message.message_id)
    if not data_list:
        bot.edit_message_text("Капча не найдена в БД и закрыта.", call_msg.message.chat.id, call_msg.message.message_id)
        return
    if data_list[0][1] != str(call_msg.from_user.id):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Вы не можете решать чужую капчу!', show_alert=True)
        return

    if int(call_msg.data.split("_")[1]) != data_list[0][2]:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Неправильный ответ!', show_alert=True)
        return

    sqlWorker.captcha(call_msg.message.message_id, remove=True)
    sqlWorker.abuse_update(data_list[0][1], timer=3600, force=True)
    sqlWorker.marmalade_remove(data_list[0][1])
    try:
        bot.restrict_chat_member(call_msg.message.chat.id, data_list[0][1],
                                 None, True, True, True, True, True, True, True, True)
    except telebot.apihelper.ApiTelegramException:
        bot.edit_message_text(f"Я не смог снять ограничения с пользователя {data_list[0][3]}! Недостаточно прав?",
                              call_msg.message.chat.id, call_msg.message.message_id)
        return

    try:
        bot.edit_message_text(utils.welcome_msg_get(data_list[0][3], call_msg.message), call_msg.message.chat.id,
                              call_msg.message.message_id)
    except telebot.apihelper.ApiTelegramException:
        pass
