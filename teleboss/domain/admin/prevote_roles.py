import logging
import telebot
from teleboss.shared.parsers import (
    html_fix,
    topic_reply_fix,
    username_parser,
    username_parser_chat_member,
)
from teleboss.shared.runtime import bot, data
from teleboss.voting.bases import PreVote

class Rank(PreVote):
    vote_type = "rank"

    pre_return = PreVote.pre_return_command_forbidden

    def direct_fn(self):
        bot.reply_to(self.message, "Звание не может быть пустым.")

    def arg_fn(self, arg):
        if topic_reply_fix(self.message.reply_to_message) is None:
            self.me()
            return
        elif self.message.reply_to_message.from_user.id == self.message.from_user.id:
            self.me()
            return

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение бота, звание которого вы хотите сменить.")
            return

        if self.message.reply_to_message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу менять звание анонимных администраторов!")
            return

        if not self.message.reply_to_message.from_user.is_bot:
            bot.reply_to(self.message, "Вы не можете менять звание других пользователей (кроме ботов).")
            return

        if bot.get_chat_member(data.main_chat_id, self.message.reply_to_message.from_user.id).status != "administrator":
            bot.reply_to(self.message, "Данный бот не является администратором.")
            return

        if data.bot_id == self.message.reply_to_message.from_user.id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        self.unique_id = str(self.message.reply_to_message.from_user.id) + "_rank"
        if self.is_voting_exist():
            return

        rank_text = self.msg_txt.split(maxsplit=1)[1]

        if len(rank_text) > 16:
            bot.reply_to(self.message, "Звание не может быть длиннее 16 символов.")
            return

        self.vote_text = ("Тема голосования: смена звания бота " +
                          username_parser(self.message.reply_to_message, True) +
                          f" на \"{html_fix(rank_text)}\""
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.message.reply_to_message.from_user.id,
                          username_parser(self.message.reply_to_message),
                          rank_text, username_parser(self.message)]

        self.poll_maker()

    def me(self):
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "administrator":

            rank_text = self.msg_txt.split(maxsplit=1)[1]

            if len(rank_text) > 16:
                bot.reply_to(self.message, "Звание не может быть длиннее 16 символов.")
                return

            try:
                bot.set_chat_administrator_custom_title(data.main_chat_id, self.message.from_user.id, rank_text)
                bot.reply_to(self.message, "Звание \"" + rank_text + "\" успешно установлено пользователю "
                             + username_parser(self.message, True) + ".")
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.reply_to(self.message, "В звании не поддерживаются эмодзи.")
                    return
                logging.error(f'Error when changing administrator title!\n{e}')
                bot.reply_to(self.message, "Не удалось сменить звание.")
            return
        elif bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "creator":
            bot.reply_to(self.message, "Я не могу изменить звание создателя чата.")
            return
        else:
            bot.reply_to(self.message, "Вы не являетесь администратором.")
            return

class Deop(PreVote):
    vote_type = "deop"

    pre_return = PreVote.pre_return_command_forbidden

    def direct_fn(self):
        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message,
                         "Ответьте на сообщение, используйте аргумент \"me\" или номер админа из списка /op list")
            return

        if topic_reply_fix(self.message.reply_to_message) is not None:
            if self.message.reply_to_message.from_user.id == self.message.from_user.id:
                self.me()
            else:
                self.reply_msg_target()
                self.pre_vote()

    def arg_fn(self, arg):
        if arg == "me":
            self.me()
        elif arg.isdigit():
            index = int(arg) - 1
            admin_list = bot.get_chat_administrators(data.main_chat_id)
            try:
                if index < 0:
                    raise IndexError
                admin = admin_list[index]
            except IndexError:
                bot.reply_to(self.message, "Админ с указанным индексом не найден")
                return
            if admin.is_anonymous and not admin.user.is_bot:
                admin_title = f'"{admin.custom_title}"' if admin.custom_title else "отсутствует"
                self.reply_username = f'ANONYMOUS (звание {admin_title})'
            else:
                self.reply_username = username_parser_chat_member(admin)
            self.reply_user_id = admin.user.id
            self.pre_vote()
        else:
            bot.reply_to(self.message, "Неизвестный аргумент команды.")
            return

    def pre_vote(self):
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, f"{self.reply_username} является создателем чата, я не могу снять его права.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status != "administrator":
            bot.reply_to(self.message, f"{self.reply_username} не является администратором!")
            return

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу снять права анонимного администратора таким образом! "
                                       "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                                       "Список администраторов вы можете получить командой /op list.")
            return

        self.unique_id = str(self.reply_user_id) + "_deop"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: снятие прав администратора с {html_fix(self.reply_username)}"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username]
        self.poll_maker()

    def me(self):
        if self.message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу снять права анонимного администратора таким образом! "
                                       "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                                       "Список администраторов вы можете получить командой /op list.")
            return
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "creator":
            bot.reply_to(self.message, "Вы являетесь создателем чата, я не могу снять ваши права.")
            return
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status != "administrator":
            bot.reply_to(self.message, "Вы не являетесь администратором!")
            return
        try:
            bot.promote_chat_member(data.main_chat_id, self.message.from_user.id, can_manage_chat=False)
            bot.reply_to(self.message, "Пользователь " + username_parser(self.message) +
                         " добровольно ушёл в отставку.\nСпасибо за верную службу!")
            return
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error when changing administrator rights!\n{e}')
            bot.reply_to(self.message, "Я не могу изменить ваши права!")
            return
