import time
from typing import Optional
from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import (
    formatted_timer,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote
from teleboss.voting.engine import poll_engine

class PrivateMode(PreVote):
    help_text = "Существуют три режима приватности чата:\n" \
                "1. Использование вайтлиста и системы инвайтов. Участник, не найденный в вайтлисте или в " \
                "одном из союзных чатов, блокируется. Классическая схема, применяемая для приватных чатов.\n" \
                "2. Использование голосования при вступлении участника. При вступлении участника в чат " \
                "отправка от него сообщений ограничивается, выставляется голосование за возможность " \
                "его вступления в чат. По завершению голосования участник блокируется или ему позволяется " \
                "вступить в чат. Новая схема, созданная для публичных чатов.\n" \
                "3. Использование классической капчи при вступлении участника.\n" \
                "Если хостер бота выставил режим \"mixed\" в конфиге бота, можно сменить режим на другой " \
                "(команда /private 1/2/3), в противном случае хостер бота устанавливает режим работы " \
                "самостоятельно.\n<b>Текущие настройки чата:</b>" \
                "\nНастройки заблокированы хостером: {}" \
                "\nТекущий режим чата: {}{}"

    pre_return = PreVote.pre_return_command_forbidden

    def direct_fn(self):
        self.help()

    def help(self):
        if not self.help_access_check():
            return
        if data.binary_chat_mode == 0:
            chat_mode = "приватный"
        elif data.binary_chat_mode == 1:
            chat_mode = "публичный (с голосованием)"
        else:
            chat_mode = "публичный (с капчёй)"

        chat_mode_locked = "да" if data.chat_mode != "mixed" else "нет"
        shield_info = ""
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            shield_info = "\n<b>Внимание! Включён режим защиты чата (подробнее - /shield)</b>\n" \
                          f"До отключения осталось {formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text.format(chat_mode_locked, chat_mode, shield_info), parse_mode="html")

    def arg_fn(self, arg):
        if data.chat_mode != "mixed":
            bot.reply_to(self.message, "Хостер бота заблокировал возможность сменить режим работы бота.")
            return

        self.unique_id = "private mode"
        if self.is_voting_exist():
            return

        try:
            chosen_mode = int(arg) - 1
            if not 0 <= chosen_mode <= 2:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 1 до 3).")
            return

        if chosen_mode == data.binary_chat_mode:
            bot.reply_to(self.message, "Данный режим уже используется сейчас!")
            return

        chat_modes = ["приватный", "публичный (с голосованием)", "публичный (с капчёй)"]
        chat_mode = chat_modes[chosen_mode]

        self.vote_text = (f"Тема голосования: изменение режима приватности чата на {chat_mode}."
                          f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [chosen_mode, username_parser(self.message, True), chat_mode]
        self.poll_maker()

class Votes(PreVote):
    help_text = ("Используйте эту команду без аргументов, чтобы посмотреть список текущих голосований в данном чате.\n"
                 'Используйте аргумент "public", "private" или "hidden" для переключения режимов приватности '
                 'голосования.\nВсего существуют три режима:\n'
                 '1. Публичный (public) - всем участникам видно, кто и за какой вариант проголосовал (с помощью кнопки '
                 '"Список голосов"), а так же отображается счётчик голосов, оставленных за каждый из вариантов.\n'
                 '2. Приватный (private) - участникам виден только счётчик голосов для каждого варианта, но они могут '
                 'узнать, за какой вариант оставили голос, с помощью кнопки "Узнать мой голос".\n'
                 '3. Скрытый (hidden) - счётчик голосов для каждого варианта скрыт, но узнать свой голос с помощью '
                 'кнопки участники по прежнему могут. Используется для классического тайного голосования.\n\n'
                 '<b>В режимах "приватный" и "скрытый" ID проголосовавшего участника хэшируется в БД с использованием '
                 'значения <i>chat_instance</i>, уникального для каждого чата и экземпляра бота. Узнать данное '
                 'значение владелец бота может только при вмешательстве в работу экземпляра бота или установке плагина '
                 'с функцией просмотра chat_instance. В случае компрометации данного значения для восстановления '
                 'анонимности голосований настоятельно рекомендуется пересоздать бота для получения нового '
                 'chat_instance.\nТем не менее, в связи с техническими ограничениями владелец бота в любом случае '
                 'может посмотреть в БД <i>количество</i> голосов, отданных за определённый вариант .</b>\n\n'
                 'Вы можете использовать ключ --private, --public или --hidden (обязательно вторым словом) в '
                 'отправляемой боту команде, чтобы перезаписать глобальные настройки приватности для любого '
                 'создаваемого вами голосования. Например, команда <code>/title --public Тестовый чат</code> создаст '
                 'публичный опрос, даже если в чате глобально включен режим приватности голосований.\n'
                 '<b>Текущий статус приватности голосований</b>: {}')

    def pre_return(self) -> Optional[bool]:
        if (not bot_name_checker(self.message) or
                command_forbidden(self.message, not_in_private_dialog=True)):
            return True
        return None

    def help(self):
        status = {"public": "публичные", "private": "приватные", "hidden": "скрытые"}
        bot.reply_to(self.message, self.help_text.format(status[data.vote_privacy]), parse_mode="html")

    def direct_fn(self):
        records = sqlWorker.get_all_polls()
        poll_list = ""
        number = 1

        if bot.get_chat(self.message.chat.id).username is not None:
            format_chat_id = bot.get_chat(self.message.chat.id).username
        else:
            format_chat_id = f"c/{str(self.message.chat.id)[4:]}"

        for record in records:
            if record[3] != self.message.chat.id:
                continue
            record_chat_id = format_chat_id
            if self.message.chat.is_forum:
                thread_id = f'/{record[9]}' if record[9] else '/1'
                record_chat_id = format_chat_id + thread_id
            try:
                vote_type = poll_engine.post_vote_list[record[2]].description
            except KeyError:
                vote_type = "INVALID (не загружен плагин?)"
            poll_list = poll_list + f"{number}. https://t.me/{record_chat_id}/{record[1]}, " \
                                    f"тип - {vote_type}, " \
                                    f"до завершения – {formatted_timer(record[5] - int(time.time()))}\n"
            number = number + 1

        if poll_list == "":
            poll_list = "В этом чате нет активных голосований!"
        else:
            poll_list = "Список активных голосований:\n" + poll_list

        bot.reply_to(self.message, poll_list)

    def set_args(self) -> dict:
        return {"private": self.vote_privacy_private,
                "public": self.vote_privacy_public,
                "hidden": self.vote_privacy_hidden}

    def vote_privacy_private(self):
        if data.vote_privacy == 'private':
            bot.reply_to(self.message, "Голосования уже являются приватными!")
            return
        self.vote_privacy('private')

    def vote_privacy_public(self):
        if data.vote_privacy == 'public':
            bot.reply_to(self.message, "Голосования уже являются публичными!")
            return
        self.vote_privacy('public')

    def vote_privacy_hidden(self):
        if data.vote_privacy == 'hidden':
            bot.reply_to(self.message, "Голосования уже являются скрытыми!")
            return
        self.vote_privacy('hidden')

    def vote_privacy(self, vote_privacy_mode):
        if self.is_voting_exist():
            return
        self.vote_type = "vote_privacy"
        self.unique_id = self.vote_type
        vote_privacy_text = {'private': 'приватный', 'public': 'публичный', 'hidden': 'скрытый'}
        self.vote_text = (f"Тема голосования: глобальное переключение голосований в "
                          f"{vote_privacy_text[vote_privacy_mode]} режим.\n"
                          f"<b>Режим приватности уже запущенных голосований не будет переключен.</b>\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [vote_privacy_mode, username_parser(self.message)]
        self.poll_maker()
