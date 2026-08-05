import time
from typing import Optional
from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    html_fix,
    time_parser,
    topic_reply_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class Ban(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return PreVote.timer_votes_init_ban()

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которого требуется забанить.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу заблокировать анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True
        return None

    def arg_fn(self, arg):
        restrict_timer = time_parser(extract_arg(self.msg_txt, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if extract_arg(self.msg_txt, 2) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=2)[2]
        self.ban(restrict_timer, True, f"\nПредложенный срок блокировки: {formatted_timer(restrict_timer)}", 1)

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.ban(0, False, "\nПредложенный срок блокировки: <b>перманентный</b>", 2)

    def ban(self, restrict_timer, kick_user, ban_timer_text, vote_type):

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "left" and kick_user:
            bot.reply_to(self.message, "Пользователя нет в чате, чтобы можно было кикнуть его.")
            return

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "блокировка пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            vote_theme = "изменение срока блокировки пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = f"Тема голосования: {vote_theme} {html_fix(self.reply_username)}" + \
                         date_unban + html_fix(self.ban_reason) + ban_timer_text + \
                         f"\nИнициатор голосования: {username_parser(self.message, True)}."

        self.vote_args = [self.reply_user_id, self.reply_username, username_parser(self.message),
                          vote_type, restrict_timer, self.ban_reason]

        self.poll_maker()

class Kick(Ban):

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.ban(3600, True, f"\nПредложенный срок блокировки: {formatted_timer(3600)}", 1)

class Mute(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return PreVote.timer_votes_init_ban()

    def pre_return(self) -> Optional[bool]:

        if not bot_name_checker(self.message) or command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется замутить.")
            return True

        self.reply_msg_target()
        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу ограничить анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            bot.reply_to(self.message, "Данный пользователь уже забанен или кикнут.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True
        return None

    def direct_fn(self):
        if extract_arg(self.msg_txt, 1) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=1)[1]
        self.mute(0, "\nПредложенный срок ограничений: перманентно")

    def arg_fn(self, arg):
        restrict_timer = time_parser(extract_arg(self.msg_txt, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if extract_arg(self.msg_txt, 2) is not None:
            self.ban_reason = self.msg_txt.split(maxsplit=2)[2]
        self.mute(restrict_timer, f"\nПредложенный срок ограничений: {formatted_timer(restrict_timer)}")

    def mute(self, restrict_timer, ban_timer_text):

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "ограничение сообщений пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            vote_theme = "изменение срока ограничения сообщений пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = (f"Тема голосования: {vote_theme} {html_fix(self.reply_username)}" +
                          date_unban + html_fix(self.ban_reason) + ban_timer_text +
                          f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username,
                          username_parser(self.message), 0, restrict_timer, self.ban_reason]
        self.poll_maker()

class Unban(PreVote):
    vote_type = "unban"

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется "
                                       "размутить, разбанить или обнулить значение абуза инвайта.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу разблокировать анонимного администратора!")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status not in ("restricted", "kicked") and \
                sum(sqlWorker.abuse_check(self.reply_user_id)) == 0:
            bot.reply_to(self.message, "Данный пользователь не ограничен.")
            return True
        return None

    def direct_fn(self):
        self.unique_id = str(self.reply_user_id) + "_unban"
        if self.is_voting_exist():
            return

        self.vote_text = ("Тема голосования: снятие ограничений с пользователя "
                          + html_fix(self.reply_username) +
                          f".\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username, username_parser(self.message)]
        self.poll_maker()
