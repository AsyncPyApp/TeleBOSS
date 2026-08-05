import logging
import traceback

from teleboss.shared.runtime import bot, data, helper


@bot.callback_query_handler(func=lambda call: "help!_cat" in call.data)
def help_category(call_msg):

    if bot.get_chat_member(data.main_chat_id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id, # for private messages
                                  text='У вас нет прав для использования этой команды.', show_alert=True)
        return

    index = call_msg.data.split("_")[2]
    try:
        help_cat_text, help_cat_keyboard = helper.get_category_list(index)
        bot.edit_message_text(help_cat_text, call_msg.message.chat.id, call_msg.message.message_id,
                              reply_markup=help_cat_keyboard, parse_mode='html')
    except Exception as e:
        if "Category index not found" in str(e):
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Индекс категории не найден! Отправьте новое сообщение командой /help.')
            return
        elif "Too Many Requests" in str(e):
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Слишком много запросов, повторите попытку через '
                                           f'{str(e).split(" ")[-1]} секунд.', show_alert=True)
            return
        logging.error(f"{e}\n{traceback.format_exc()}")
        bot.edit_message_text("Ошибка получения информации из JSON-файла помощи по командам! Информация об ошибке "
                              "сохранена в логи бота.", call_msg.message.chat.id, call_msg.message.message_id)

@bot.callback_query_handler(func=lambda call: "help!_main" in call.data)
def help_main(call_msg):

    if bot.get_chat_member(data.main_chat_id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id, # for private messages
                                  text='У вас нет прав для использования этой команды.', show_alert=True)
        return

    extended_help = ("\n<b>Форматирование времени (не зависит от регистра):</b>\n"
                     "<blockquote expandable>без аргумента или s - секунды\n"
                     "m - минуты\n"
                     "h - часы\n"
                     "d - дни\n"
                     "w - недели\n"
                     "Примеры использования: /abuse 12h30s, /timer 3600, /kickuser 30m12d12d</blockquote>\n\n"
                     "<b>Ключи --private и --public позволяют перезаписать настройки приватности для создаваемого "
                     "голосования (подробнее см. /votes help)</b>")

    try:
        help_main_text, help_main_keyboard = helper.get_main_list()
        bot.edit_message_text(help_main_text + extended_help, call_msg.message.chat.id, call_msg.message.message_id,
                              reply_markup=help_main_keyboard, parse_mode='html')
    except Exception as e:
        if "Too Many Requests" in str(e):
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Слишком много запросов, повторите попытку через '
                                           f'{str(e).split(" ")[-1]}с.', show_alert=True)
            return
        logging.error(f"{e}\n{traceback.format_exc()}")
        bot.edit_message_text("Ошибка получения информации из JSON-файла помощи по командам! Информация об ошибке "
                              "сохранена в логи бота.", call_msg.message.chat.id, call_msg.message.message_id)
