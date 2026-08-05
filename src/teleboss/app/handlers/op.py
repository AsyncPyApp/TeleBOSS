"""Callback handlers for ``op!`` checklist buttons."""

import json

from teleboss.app.handlers.votes import call_msg_chk, close_vote
from teleboss.domain.admin.prevote import Op, OpGlobal
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.shared.storage.sql_worker import ApplyVoteStatus
from teleboss.shared.vote_ui import button_anonymous_checker, make_keyboard
from teleboss.voting.engine import poll_engine


class _OpSoftReject(Exception):
    """User-facing op mutation rejection inside an ``apply_vote`` mutator."""


@bot.callback_query_handler(func=lambda call: "op!" in call.data)
def op_button(call_msg):
    """Toggle op checklist buttons via atomic storage mutation.

    Args:
        call_msg: Telegram callback query whose ``data`` contains ``op!``.
    """
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
    if button_anonymous_checker(call_msg.from_user.id, call_msg.message.chat.id):
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

    chat_id = call_msg.message.chat.id
    message_id = call_msg.message.id
    soft_alert: list[str] = []
    mutate_ctx: dict = {
        "button_data": None,
        "confirmed": False,
        "poll_type": poll[0][2],
    }

    def mutator(poll_row) -> str:
        """Apply the matching ``op!`` toggle and return buttons JSON.

        Args:
            poll_row: Open poll row locked by ``apply_vote``.

        Returns:
            Serialized buttons JSON after the toggle.

        Raises:
            _OpSoftReject: When the click is rejected without mutation.
        """
        local_buttons = json.loads(poll_row[4])
        poll_type = poll_row[2]
        for button in local_buttons:
            if button["button_type"] != call_msg.data:
                continue
            if call_msg.data == "op!_confirmed":
                button.update({"value": not button["value"]})
                mutate_ctx["button_data"] = local_buttons
                mutate_ctx["confirmed"] = True
                mutate_ctx["poll_type"] = poll_type
                return json.dumps(local_buttons)
            right_key = button["button_type"].split("_", maxsplit=1)[1]
            if not data.admin_allowed[right_key] and poll_type == "op setup":
                soft_alert.append(
                    "Выдача данного права запрещена на глобальном уровне!"
                )
                raise _OpSoftReject()
            if not button["value"]:
                allowed = "✅"
            else:
                allowed = "❌"
            button.update(
                {"value": not button["value"], "name": f"{button['name'][:-1]}{allowed}"}
            )
            break

        mutate_ctx["button_data"] = local_buttons
        mutate_ctx["confirmed"] = False
        mutate_ctx["poll_type"] = poll_type
        return json.dumps(local_buttons)

    result = sqlWorker.apply_vote(chat_id, message_id, mutator)

    if soft_alert:
        bot.answer_callback_query(
            callback_query_id=call_msg.id, text=soft_alert[0], show_alert=True
        )
        return

    if result.status in (ApplyVoteStatus.NOT_FOUND, ApplyVoteStatus.NOT_OPEN):
        bot.answer_callback_query(
            callback_query_id=call_msg.id,
            text="Данный чек-лист не найден в БД.",
            show_alert=True,
        )
        return

    if result.status != ApplyVoteStatus.OK or result.poll is None:
        bot.answer_callback_query(
            callback_query_id=call_msg.id,
            text="Не удалось сохранить изменение. Попробуйте ещё раз.",
            show_alert=True,
        )
        return

    poll_row = result.poll
    button_data = mutate_ctx["button_data"]
    if button_data is None:
        button_data = json.loads(poll_row[4])

    if mutate_ctx["confirmed"]:
        poll_engine.vote_abuse.clear()
        poll_engine.vote_result(poll_row[0], call_msg.message.id)
        if mutate_ctx["poll_type"] == "op setup":
            Op(call_msg.message, [poll_row])
        else:
            OpGlobal(call_msg.message, [poll_row])
        return

    bot.edit_message_reply_markup(
        call_msg.message.chat.id,
        message_id=call_msg.message.id,
        reply_markup=make_keyboard(button_data, False),
    )
