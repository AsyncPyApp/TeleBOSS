import json
import logging
import threading
import time
import telebot
from teleboss.shared.access import allowed_list
from teleboss.shared.parsers import (
    html_fix,
    reply_msg_target,
    topic_reply_fix,
    username_parser,
    username_parser_chat_member,
)
from teleboss.shared.vote_ui import make_keyboard, make_mailing
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote
from teleboss.voting.engine import poll_engine

class OpSetup(PreVote):
    vote_type = "op setup"
    help_text = "Используйте эту команду для назначения прав администратора себе, боту или другому участнику.\n" \
                "Глобальные права администраторов для чата можно изменить с помощью команды вида " \
                "/op global, если хостер бота не запретил это.\n<b>Попытка выдачи недоступных " \
                "боту или отключенных на уровне чата прав приведёт к ошибке!\n"\
                "Изменения разрешены хостером - {}\nТекущие права для чата:</b>\n{}" \
                "\n<b>ВНИМАНИЕ: при переназначении прав пользователю его текущие права перезаписываются!</b>"

    pre_return = PreVote.pre_return_command_forbidden

    def help(self):
        if self.help_access_check():
            admin_fixed = "❌" if data.admin_fixed else "✅"
            bot.reply_to(self.message, self.help_text.format(admin_fixed, allowed_list()),
                         parse_mode="html")

    def arg_fn(self, arg):  # If the command was run with arguments
        try:
            self.args[arg]()  # Runs a function from a dictionary by default
        except KeyError:
            self.direct_fn()

    def set_args(self) -> dict:
        return {"list": self.list, "global": self.global_rules}

    def list(self):
        admin_list = bot.get_chat_administrators(data.main_chat_id)
        admin_msg = bot.reply_to(self.message, "Сборка списка администраторов, ожидайте...")
        admin_list_text = "Список текущих администраторов чата:" if admin_list else "В чате нет администраторов!"
        counter = 0
        for admin in admin_list:
            counter += 1
            admin_list_text += f"\n{counter}. "
            admin_title = f'"{admin.custom_title}"' if admin.custom_title else "отсутствует"
            if admin.is_anonymous and not admin.user.is_bot:
                admin_list_text += f'Анонимный администратор (звание {admin_title})'
            else:
                admin_list_text += username_parser_chat_member(admin)
            if admin.status == "creator":
                admin_list_text += " - автор чата"
        bot.edit_message_text(admin_list_text, admin_msg.chat.id, admin_msg.id)
        return

    def global_rules(self):
        if data.admin_fixed:
            bot.reply_to(self.message, "Изменение глобальных прав администраторов для чата заблокировано хостером.")
            return

        self.unique_id = "global op setup"
        self.vote_type = self.unique_id
        for unique_id in (self.unique_id, "global op"):
            if self.is_voting_exist_op(unique_id):
                return

        self.vote_text = f"Выберите разрешённые права для администраторов чата на глобальном уровне:"
        self.vote_args = [username_parser(self.message, True), self.user_id]
        self.poll_maker(current_timer=86400, silent=True)

    def get_votes_text(self):
        return self.vote_text

    def direct_fn(self):
        if topic_reply_fix(self.message.reply_to_message) is None:
            self.reply_user_id, self.reply_username, _ = reply_msg_target(self.message)
        else:
            self.reply_user_id, self.reply_username, _ = reply_msg_target(self.message.reply_to_message)

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу менять права анонимным администраторам!")
            return

        if self.reply_user_id == data.bot_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Пользователь является создателем чата.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status in ("left", "kicked"):
            bot.reply_to(self.message, "Пользователь не состоит в чате.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            bot.reply_to(self.message, "Пользователь с ограниченными правами не может стать админом.")
            return

        self.unique_id = f"{self.reply_user_id}_op_setup"
        for unique_id in (f"{self.reply_user_id}_op_setup", f"{self.reply_user_id}_op"):
            if self.is_voting_exist_op(unique_id):
                return

        self.vote_text = f"Выберите разрешённые права для администратора {html_fix(self.reply_username)}:"
        self.vote_args = [username_parser(self.message, True), self.user_id,
                          self.reply_username, self.reply_user_id]
        self.poll_maker(current_timer=86400, silent=True)

    def get_buttons_scheme(self):
        button_scheme = []
        for name, value in data.admin_allowed.items():
            if value:
                allowed = "✅"
            elif self.unique_id == "global op setup":
                allowed = "❌"
            else:
                allowed = "🔒"
            button_scheme.append({"button_type": f"op!_{name}",
                                  "name": f"{data.admin_rus[name]} {allowed}",
                                  "value": value})
        button_scheme.append({"button_type": "row_width", "row_width": 1})  # Меня вынудили.
        button_scheme.append({"button_type": "op!_confirmed", "name": "Подтвердить", "value": False})
        button_scheme.append({"button_type": "op!_close", "name": "Закрыть чек-лист", "user_id": self.user_id})
        return button_scheme

    def is_voting_exist_op(self, unique_id):
        message_id = sqlWorker.get_message_id(unique_id)
        if message_id:
            poll = sqlWorker.get_poll(message_id)
            if poll[0][5] <= int(time.time()):
                sqlWorker.rem_rec(poll[0][0])
                return False
            else:
                bot.reply_to(self.message, "Голосование о данном вопросе уже идёт.")
                return True
        return False

class Op(PreVote):
    vote_type = "op"

    def __init__(self, message, poll):
        super().__init__(message)
        buttons_data = json.loads(poll[0][4])
        self.rights_text = ""
        self.rights_data = {}
        for button in buttons_data:
            if "op!" in button["button_type"] and button["button_type"] not in ("op!_confirmed", "op!_close"):
                self.rights_text += f'\n{button["name"]}'
                self.rights_data.update({button["button_type"].split('_', maxsplit=1)[1]: button["value"]})
        if self.vote_type == 'op':
            self.rights_data.update({"can_manage_chat": True})
        self.data_list = json.loads(poll[0][6])
        self.user_id = self.data_list[1]
        buttons_scheme = self.get_buttons_scheme()
        self.vote_text = self.op_vote_text()
        self.hidden = bool(poll[0][8])
        topic_id = poll[0][9]
        bot.edit_message_text(self.get_votes_text(), message.chat.id, message.id,
                              reply_markup=make_keyboard(buttons_scheme, self.hidden), parse_mode='html')
        sqlWorker.add_poll(self.unique_id(), message.id, self.vote_type, message.chat.id,
                           json.dumps(buttons_scheme), int(time.time()) + self.current_timer,
                           json.dumps(self.vote_args()), self.current_votes, self.hidden, topic_id)
        try:
            bot.pin_chat_message(message.chat.id, message.id, disable_notification=True)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't pin message in chat {message.chat.id}!\n{e}")
        threading.Thread(target=make_mailing, daemon=True,
                         args=(poll_engine.post_vote_list[self.vote_type].description, message.id,
                               self.current_timer)).start()
        threading.Thread(target=poll_engine.vote_timer, daemon=True,
                         args=(self.current_timer, self.unique_id(), message.id)).start()

    def arg_fn(self, _):
        return

    def op_vote_text(self):
        return f"Тема голосования: выдача/изменение прав администратора пользователю "\
               f"{html_fix(self.data_list[2])}"\
               f"\nПрава, выбранные для выдачи пользователю:{self.rights_text}"\
               f"\nИнициатор голосования: {html_fix(self.data_list[0])}."\
               "\n<b>Звание можно будет установить ПОСЛЕ закрытия голосования.</b>"

    def vote_args(self):
        return [self.data_list[3], self.data_list[2], self.rights_data]

    def unique_id(self):
        return f"{self.data_list[3]}_op"

class OpGlobal(Op):
    vote_type = "global op permissions"

    def op_vote_text(self):
        return f"Тема голосования: смена разрешённых для выдачи пользователям прав." \
               f"\nПрава, выбранные для выдачи пользователям:{self.rights_text}" \
               f"\nИнициатор голосования: {html_fix(self.data_list[0])}."

    def vote_args(self):
        return [self.rights_data]

    def unique_id(self):
        return "global op"
