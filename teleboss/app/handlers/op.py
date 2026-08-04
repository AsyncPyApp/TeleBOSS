import json

import prevote
import utils
from poll_engines import poll_engine
from utils import data, bot, sqlWorker

from teleboss.app.handlers.votes import call_msg_chk, close_vote


@bot.callback_query_handler(func=lambda call: "op!" in call.data)
def op_button(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Бот работает в режиме инициализации!', show_alert=True)
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text=f'Данный чек-лист не найден в БД.', show_alert=True)
        return

    user_id = call_msg.from_user.id
    if utils.button_anonymous_checker(call_msg.from_user.id, call_msg.message.chat.id):
        user_id = data.ANONYMOUS_ID

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "op!_close":
            if button["user_id"] != user_id:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text='Вы не можете взаимодействовать с чужим чек-листом!', show_alert=True)
                return

    if call_msg.data == "op!_close":
        close_vote(call_msg)
        return

    # The ability to create checklists for anonymous admins remains, but without the ability to verify them

    for button in button_data:
        if button["button_type"] != call_msg.data:
            continue
        if call_msg.data == "op!_confirmed":
            button.update({'value': not button['value']})
            sqlWorker.update_poll_votes(poll[0][0], json.dumps(button_data))
            poll_engine.vote_abuse.clear()
            poll_engine.vote_result(poll[0][0], call_msg.message.id)
            if poll[0][2] == 'op setup':
                prevote.Op(call_msg.message, poll)
            else:
                prevote.OpGlobal(call_msg.message, poll)
            return
        if not data.admin_allowed[button["button_type"].split("_", maxsplit=1)[1]] and poll[0][2] == 'op setup':
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text="Выдача данного права запрещена на глобальном уровне!", show_alert=True)
            return
        if not button['value']:
            allowed = "✅"
        else:
            allowed = "❌"
        button.update({'value': not button['value'], 'name': f"{button['name'][:-1]}{allowed}"})
        break

    sqlWorker.update_poll_votes(poll[0][0], json.dumps(button_data))
    bot.edit_message_reply_markup(call_msg.message.chat.id, message_id=call_msg.message.id,
                                  reply_markup=utils.make_keyboard(button_data, False))
