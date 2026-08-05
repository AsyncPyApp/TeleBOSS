from typing import Optional
from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    html_fix,
    reply_msg_target,
    topic_reply_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class MessageRemover(PreVote):
    warn = ""
    clear = ""
    vote_type = "delete message"

    @staticmethod
    def timer_votes_init():
        return PreVote.timer_votes_init_ban()

    def pre_return(self) -> Optional[bool]:
        """Reject delete-message votes that target an open bot poll message.

        Uses composite ``(chat_id, message_id)`` lookup so a same-id poll in
        another chat cannot block deletion here.

        Returns:
            ``True`` when the command should abort; ``None`` to continue.
        """
        if command_forbidden(self.message):
            return True

        if topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которое требуется удалить.")
            return True

        self.reply_user_id, self.reply_username, self.reply_is_bot \
            = reply_msg_target(self.message.reply_to_message)

        reply = self.message.reply_to_message
        if data.bot_id == self.reply_user_id and sqlWorker.get_open_poll(
            self.message.chat.id, reply.id
        ):
            bot.reply_to(self.message, "Вы не можете удалить голосование до его завершения!")
            return True

        if all([data.bot_id != self.reply_user_id, self.reply_is_bot, self.reply_user_id != data.ANONYMOUS_ID]):
            bot.reply_to(self.message, f"Боты в Telegram не могут удалять сообщения других ботов!")
            return True
        return None

    def direct_fn(self):
        self.unique_id = str(self.message.reply_to_message.message_id) + "_delmsg"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: удаление сообщения пользователя {html_fix(self.reply_username)}"
                          f".\nИнициатор голосования: {username_parser(self.message, True)}." + self.warn)
        self.vote_args = [self.message.reply_to_message.message_id, self.reply_username, self.silent]
        self.poll_maker(silent=self.silent)

class MessageSilentRemover(MessageRemover):
    warn = "\n\n<b>Внимание, голосования для бесследной очистки не закрепляются автоматически. Пожалуйста, " \
           "закрепите их самостоятельно при необходимости.</b>\n"
    silent = True
    clear = "бесследно "

    @staticmethod
    def timer_votes_init():
        return data.global_timer, data.thresholds_get()
