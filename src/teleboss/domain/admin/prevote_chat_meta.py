import logging
import traceback
from typing import Optional
from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    html_fix,
    topic_reply_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data
from teleboss.voting.bases import PreVote

class RemoveTopic(PreVote):
    vote_type = "remove topic"

    @staticmethod
    def timer_votes_init():
        return 86400, data.thresholds_get()

    def pre_return(self) -> Optional[bool]:

        if command_forbidden(self.message):
            return True

        if not self.message.chat.is_forum:
            bot.reply_to(self.message, "Данный чат НЕ является форумом!")
            return True

        if self.message.message_thread_id is None or not self.message.is_topic_message:
            bot.reply_to(self.message, "Данный чат НЕ является топиком или является основным топиком!")
            return True

        if not self.message.reply_to_message.forum_topic_created:
            bot.reply_to(self.message, "Пожалуйста, не используйте реплей при использовании этой команды. "
                                       "Из-за особенностей Telegram API она обрабатывается некорректно.")
            return True
        return None

    def direct_fn(self):
        self.unique_id = str(self.message.message_thread_id) + "_rem_topic"
        if self.is_voting_exist():
            return

        self.vote_text = ("Тема голосования: удаление данного топика"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.message.message_thread_id, username_parser(self.message),
                          self.message.reply_to_message.forum_topic_created.name]
        self.poll_maker()

class Title(PreVote):
    unique_id = "title"
    vote_type = unique_id

    pre_return = PreVote.pre_return_command_forbidden

    def direct_fn(self):
        bot.reply_to(self.message, "Название чата не может быть пустым.")

    def arg_fn(self, arg):
        if len(self.msg_txt.split(maxsplit=1)[1]) > 255:
            bot.reply_to(self.message, "Название не должно быть длиннее 255 символов!")
            return

        if bot.get_chat(data.main_chat_id).title == self.msg_txt.split(maxsplit=1)[1]:
            bot.reply_to(self.message, "Название чата не может совпадать с существующим названием!")
            return

        if self.is_voting_exist():
            return

        self.vote_text = ("От пользователя " + username_parser(self.message, True)
                          + " поступило предложение сменить название чата на \""
                          + html_fix(self.msg_txt.split(maxsplit=1)[1]) + "\".")
        self.vote_args = [self.msg_txt.split(maxsplit=1)[1], username_parser(self.message)]
        self.poll_maker()

class Description(PreVote):
    unique_id = "description"
    vote_type = unique_id
    help_text = "Для установки описания чата следует реплейнуть командой " \
                "по сообщению с текстом описания или ввести его как аргумент команды."

    pre_return = PreVote.pre_return_command_forbidden

    def arg_fn(self, _):
        description_text = self.msg_txt.split(maxsplit=1)[1]
        if len(description_text) > 255:
            bot.reply_to(self.message, "Описание не должно быть длиннее 255 символов!")
            return
        self.description(description_text)

    def direct_fn(self):
        if topic_reply_fix(self.message.reply_to_message) is not None:
            if self.message.reply_to_message.text is not None:
                description_text = self.message.reply_to_message.text
                if len(description_text) > 255:
                    bot.reply_to(self.message, "Описание не должно быть длиннее 255 символов!")
                    return
            else:
                bot.reply_to(self.message, "В отвеченном сообщении не обнаружен текст!")
                return
        else:
            description_text = ""
        self.description(description_text)

    def description(self, description_text):
        if bot.get_chat(data.main_chat_id).description == description_text:
            bot.reply_to(self.message, "Описание чата не может совпадать с существующим описанием!")
            return

        formatted_desc = " пустое" if description_text == "" else f":\n<code>{html_fix(description_text)}</code>"
        self.vote_text = (f"Тема голосования: смена описания чата на{formatted_desc}\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        if self.is_voting_exist():
            return
        self.vote_args = [description_text, username_parser(self.message)]
        self.poll_maker()

class Avatar(PreVote):
    unique_id = "chat picture"
    vote_type = unique_id

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Пожалуйста, используйте эту команду как ответ на фотографию, файл jpg или png.")
            return True
        return None

    def direct_fn(self):
        if self.is_voting_exist():
            return

        if self.message.reply_to_message.photo is not None:
            file_buffer = (bot.download_file
                           (bot.get_file(self.message.reply_to_message.photo[-1].file_id).file_path))
        elif self.message.reply_to_message.document is not None:
            if self.message.reply_to_message.document.mime_type not in ("image/png", "image/jpeg"):
                bot.reply_to(self.message, "Документ не является фотографией")
                return
            file_buffer = (bot.download_file(bot.get_file(self.message.reply_to_message.document.file_id).file_path))
        else:
            bot.reply_to(self.message, "В сообщении не обнаружена фотография")
            return

        try:
            with open(data.path + 'tmp_img', 'wb') as tmp_img:
                tmp_img.write(file_buffer)
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            bot.reply_to(self.message, "Ошибка записи изображения в файл!")
            return

        self.vote_text = ("Тема голосования: смена аватарки чата"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [username_parser(self.message)]
        self.poll_maker()
