import logging
import threading
import time
from typing import Optional

import telebot

from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote


class AlliesList(PreVote):
    help_text = "Поддерживаются аргументы add, remove и запуск без аргументов."

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message, True):
            return True

        arg = extract_arg(self.msg_txt, 1)
        if arg in ("add", "remove") and self.message.chat.id == data.main_chat_id:
            if arg == "add":
                bot.reply_to(self.message, "Команду с таким аргументом нельзя запустить в основном чате!")
                return True
            elif arg == "remove" and extract_arg(self.msg_txt, 2) is None:
                bot.reply_to(self.message, "Команду с аргументом remove без указания "
                                           "индекса нельзя запустить в основном чате!")
                return True
        else:
            self.user_id = data.bot_id
        return None

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def add(self):
        if sqlWorker.get_ally(self.message.chat.id) is not None:
            bot.reply_to(self.message, "Данный чат уже входит в список союзников!")
            return

        abuse_chk = sum(sqlWorker.abuse_check(self.message.chat.id))
        if abuse_chk > 0:
            bot.reply_to(self.message, "Сработала защита от абуза добавления в союзники! Вам следует подождать ещё "
                         + formatted_timer(abuse_chk - int(time.time())))
            return

        invite_link = bot.get_chat(self.message.chat.id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_type = "add allies"
        self.pre_vote("установка", invite_link, "создании")

    def remove(self):
        if extract_arg(self.msg_txt, 2) is not None and self.message.chat.id == data.main_chat_id:
            self.index_remove()
            return
        elif sqlWorker.get_ally(self.message.chat.id) is None:
            bot.reply_to(self.message, "Данный чат не входит в список союзников!")
            return
        invite_link = bot.get_chat(self.message.chat.id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_type = "remove allies"
        self.pre_vote("разрыв", invite_link, "разрыве")

    def index_remove(self):
        allies = sqlWorker.get_allies()
        if not allies:
            bot.reply_to(self.message, "Список союзников данного чата пуст!")
            return

        try:
            index = int(extract_arg(self.msg_txt, 2)) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Индекс должен быть больше нуля.")
            return

        try:
            ally_id = allies[index][0]
        except IndexError:
            bot.reply_to(self.message, "Чат с данным индексом не найден в списке союзников!")
            return

        self.unique_id = f"{ally_id}_allies"
        if self.is_voting_exist():
            return
        invite_link = bot.get_chat(ally_id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_text = (f"Тема голосования: разрыв союзных отношений с чатом " +
                          f"<b>{html_fix(bot.get_chat(ally_id).title)}</b>{invite_link}\n" +
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(vote_type="remove allies", vote_args=[ally_id, None, False])

    def pre_vote(self, vote_type_text, invite_link, mode_text):
        self.unique_id = str(self.message.chat.id) + "_allies"
        if self.is_voting_exist():
            return
        thread_id = self.message.message_thread_id if self.message.is_topic_message else None
        self.vote_text = (f"Тема голосования: {vote_type_text} союзных отношений с чатом " +
                          f"<b>{html_fix(bot.get_chat(self.message.chat.id).title)}</b>{invite_link}\n" +
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(add_user=True, vote_args=[self.message.chat.id, thread_id, True])

        bot.reply_to(self.message, f"Голосование о {mode_text} союза отправлено в чат "
                                   f"<b>{html_fix(bot.get_chat(data.main_chat_id).title)}</b>.\nОно завершится "
                                   f"через {formatted_timer(self.current_timer)} "
                                   f"или ранее в зависимости от количества голосов.",
                     parse_mode="html")
        return

    def direct_fn(self):
        if sqlWorker.get_ally(self.message.chat.id) is not None:
            if sqlWorker.params("shield", default_return=0) > int(time.time()):
                bot.reply_to(self.message, "В режиме защиты инвайт-ссылка на основной чат не выдаётся!")
            else:
                invite_link = bot.get_chat(data.main_chat_id).invite_link
                if invite_link is None:
                    invite_link = "отсутствует (недостаточно прав для выдачи?)"
                else:
                    invite_link = f"- {invite_link}"
                marmalade_warning = ''
                if sqlWorker.params("marmalade", default_return=True):
                    entry_time = sqlWorker.marmalade_get(self.message.from_user.id)
                    if data.binary_chat_mode == 0 and sqlWorker.whitelist(self.message.from_user.id):
                        pass
                    elif entry_time and entry_time + data.marmalade_timer > int(time.time()):
                        marmalade_warning = (
                            "\n<b>Внимание! Так как вы вошли в союзный чат меньше 18 часов назад и включён механизм "
                            "защиты чата Marmalade, вам придётся пройти стандартную процедуру вступления в чат или "
                            f"подождать {formatted_timer(entry_time + data.marmalade_timer - int(time.time()))}"
                            f"</b>"
                        )
                bot.reply_to(self.message, f"Данный чат является союзным чатом для "
                                           f"{html_fix(bot.get_chat(data.main_chat_id).title)}.\n"
                                           f"Ссылка для вступления {invite_link}{marmalade_warning}", parse_mode="html")
            return

        if command_forbidden(self.message, text="Данную команду без аргументов можно "
                                                      "запустить только в основном чате или в союзных чатах."):
            return

        allies = sqlWorker.get_allies()
        if not allies:
            bot.reply_to(self.message, "В настоящее время у вас нет союзников.")
            return
        threading.Thread(target=self.allies_building, args=(allies,)).start()

    def allies_building(self, allies):
        allies_msg = bot.reply_to(self.message, "Сборка списка союзных чатов, ожидайте...")
        allies_text = "Список союзных чатов: \n"
        ally_counter = 0
        for ally in allies:
            try:
                bot.get_chat_member(ally[0], data.bot_id).status
            except telebot.apihelper.ApiTelegramException:
                sqlWorker.remove_ally(ally[0])
                continue
            try:
                invite_link = bot.get_chat(ally[0]).invite_link
                ally_counter += 1
                if invite_link is not None:
                    allies_text = allies_text + \
                                  f'{ally_counter}. <a href="{invite_link}">' \
                                  f'{html_fix(bot.get_chat(ally[0]).title)}</a>\n'
                else:
                    allies_text = allies_text + \
                                  f"{ally_counter}. {html_fix(bot.get_chat(ally[0]).title)} " \
                                  f"(пригласительная ссылка отсутствует)\n"
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error while assembling the list of allies!\n{e}')

        if ally_counter == 0:
            bot.edit_message_text("В настоящее время у вас нет союзников.",
                                  chat_id=allies_msg.chat.id, message_id=allies_msg.id, parse_mode='html')
        else:
            bot.edit_message_text(allies_text, disable_web_page_preview=True, parse_mode='html',
                                  chat_id=allies_msg.chat.id, message_id=allies_msg.id)

    def help_access_check(self):
        if self.message.chat.id != data.main_chat_id and self.message.chat.id == self.message.from_user.id:
            if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                return False
        return True
