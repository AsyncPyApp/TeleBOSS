from typing import Optional
from teleboss.shared.access import command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    time_parser,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class Timer(PreVote):
    help_text = "Использовать как /timer [время] [ban или без аргумента],\n" \
                "или как /timer [время|0 (без кулдауна)|off|disable] random.\n" \
                "Подробнее о парсинге времени - см. команду /help."

    def pre_return(self) -> Optional[bool]:
        if command_forbidden(self.message, not_in_private_dialog=True):
            return True
        return None

    def help(self):
        if self.message.chat.id != data.main_chat_id:
            bot.reply_to(self.message, "Использовать как  /timer [время|0 (без кулдауна)|off|disable] random.\n"
                                       "Подробнее о парсинге времени - см. команду /help.,", parse_mode="html")
        elif self.help_access_check():
            bot.reply_to(self.message, self.help_text, parse_mode="html")

    def direct_fn(self):
        timer_text = ""
        if self.message.chat.id == data.main_chat_id:
            timer_text = formatted_timer(data.global_timer) + " для обычного голосования.\n" \
                         + formatted_timer(data.global_timer_ban) + " для голосования за бан.\n"
        abuse_random_time = sqlWorker.abuse_random(self.message.chat.id)
        if abuse_random_time == -1:
            timer_random_text = "Команда /random отключена."
        elif abuse_random_time == 0:
            timer_random_text = "Кулдаун команды /random отключён."
        else:
            timer_random_text = f"{formatted_timer(abuse_random_time)} - кулдаун команды /random."
        bot.reply_to(self.message, "Текущие пороги таймера:\n" + timer_text + timer_random_text)

    def arg_fn(self, arg):
        if extract_arg(self.msg_txt, 2) != "random":
            if command_forbidden(self.message, text="Команду с данным аргументом невозможно "
                                                          "запустить не в основном чате."):
                return
        timer_arg = time_parser(arg)
        second_arg = extract_arg(self.msg_txt, 2)
        if second_arg is None or second_arg == "ban":
            self.main_and_ban(timer_arg, second_arg)
        elif second_arg == "random":
            self.random(timer_arg)
        else:
            bot.reply_to(self.message, "Неверный второй аргумент (должен быть ban, random или пустой).")
            return

    def main_and_ban(self, timer_arg, second_arg):
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 5 секунд до 1 суток).")
            return
        elif timer_arg < 5 or timer_arg > 86400:
            bot.reply_to(self.message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
            return
        if second_arg is None:
            self.main(timer_arg)
        else:
            self.ban(timer_arg)

    def main(self, timer_arg):
        self.unique_id = "timer"
        ban_text = "таймера стандартных голосований"
        if timer_arg == data.global_timer:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def ban(self, timer_arg):
        self.unique_id = "timer for ban votes"
        ban_text = "таймера бан-голосований"
        if timer_arg == data.global_timer_ban:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def random(self, timer_arg):
        self.unique_id = "timer for random cooldown"
        ban_text = "кулдауна команды /random"
        if extract_arg(self.msg_txt, 1) in ("off", "disable"):
            timer_arg = -1
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 0 секунд до 1 часа).")
            return
        elif timer_arg < -1 or timer_arg > 3600:
            bot.reply_to(self.message, "Количество времени не может быть меньше 0 секунд и больше 1 часа.")
            return
        elif timer_arg == sqlWorker.abuse_random(self.message.chat.id):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if self.message.chat.id != data.main_chat_id:
            user_status = bot.get_chat_member(self.message.chat.id, self.message.from_user.id).status
            if user_status not in ("creator", "administrator"):
                bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
                return
            sqlWorker.abuse_random(self.message.chat.id, timer_arg)
            if timer_arg == -1:
                bot.reply_to(self.message, "Команда /random отключена.")
            elif timer_arg == 0:
                bot.reply_to(self.message, "Кулдаун команды /random отключён.")
            else:
                bot.reply_to(self.message, "Установлен порог кулдауна команды "
                                           f"/random на значение {formatted_timer(timer_arg)}")
            return

        if timer_arg == 0:
            vote_text = (f"Тема голосования: отключение кулдауна команды /random."
                         f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        elif timer_arg == -1:
            vote_text = (f"Тема голосования: отключение команды /random."
                         f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        else:
            vote_text = ""
        self.pre_vote(timer_arg, ban_text, vote_text)

    def pre_vote(self, timer_arg, ban_text, vote_text=""):
        if self.is_voting_exist():
            return
        self.vote_text = vote_text or (f"Тема голосования: смена {ban_text} на значение "
                                       + formatted_timer(timer_arg) +
                                       f"\nИнициатор голосования: {username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [timer_arg, self.unique_id]
        self.poll_maker()
