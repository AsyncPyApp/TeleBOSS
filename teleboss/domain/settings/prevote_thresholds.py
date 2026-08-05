from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    username_parser,
)
from teleboss.shared.runtime import bot, data
from teleboss.voting.bases import PreVote

class Thresholds(PreVote):
    vote_type = "threshold"
    help_text = ('Используйте команду в формате "/threshold [(число)|auto] [(пустое)|ban|min]."\n'
                 'Примеры: /threshold auto ban, /threshold 5 min, /threshold auto.\n'
                 'Если число голосов для досрочного стандартных или бан-голосований оказывается ниже минимального '
                 'порога, оно автоматически приравнивается к минимальному порогу.\n\n'
                 'Автоматический порог высчитывается по нижеследующей схеме.\n'
                 'Для досрочного завершения стандарных голосований:\n- количество участников, делённое на 2 нацело, '
                 'но всегда меньше 8 и больше 2 и никогда не ниже значения минимального порога\n'
                 'Для досрочного завершения бан-голосований:\n- 5 при количестве участников больше 15,\n- 3 при '
                 'количестве участников больше 5\n- 2 в ином случае, но никогда не ниже минимального порога\n'
                 'Для минимального порога принятия результатов голосования:\n- 5 при количестве '
                 'участников больше 30\n- 3 при количестве участников больше 15\n- 2 в ином случае')

    pre_return = PreVote.pre_return_command_forbidden

    @staticmethod
    def auto_thr_text(bool_):
        return " (авто)" if bool_ else ""

    def direct_fn(self):

        bot.reply_to(
            self.message,
            "<b>Текущие пороги количества голосов:</b>\n"
            "Голосов для досрочного закрытия обычного голосования требуется (за любой вариант): "
            f"{data.thresholds_get()}{self.auto_thr_text(data.is_thresholds_auto())}\n"
            "Голосов для досрочного закрытия бан-голосования требуется (за любой вариант): "
            f"{data.thresholds_get(ban=True)}{self.auto_thr_text(data.is_thresholds_auto(ban=True))}\n"
            "Суммарный минимальный порог голосов, требуемый для принятия решения: "
            f"{data.thresholds_get(minimum=True)}{self.auto_thr_text(data.is_thresholds_auto(minimum=True))}",
            parse_mode='html'
        )

    def get_votes_text(self):
        if self.unique_id == "threshold_min":
            return f"{self.vote_text}\nГолосование будет закрыто через {formatted_timer(self.current_timer)}, " \
                   f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}."

        return f"{self.vote_text}\nГолосование будет закрыто через {formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def arg_fn(self, arg):
        if arg != "auto":
            try:
                thr_value = int(arg)
            except (TypeError, ValueError):
                bot.reply_to(self.message, "Неверный аргумент (должно быть целое число от 2 до "
                             + str(bot.get_chat_members_count(data.main_chat_id)) + " или \"auto\").")
                return

            if thr_value > bot.get_chat_members_count(data.main_chat_id):
                bot.reply_to(self.message, "Количество голосов не может быть больше количества участников в чате.")
                return
            elif thr_value < 2 and not data.debug:
                bot.reply_to(self.message, "Количество голосов не может быть меньше 2")
                return
            elif thr_value < 1:
                bot.reply_to(self.message, "Количество голосов не может быть меньше 1 (в дебаг-режиме)")
                return
        else:
            thr_value = 0

        second_arg = extract_arg(self.msg_txt, 2)
        if second_arg is None:
            self.main(thr_value)
        elif second_arg == "ban":
            self.ban(thr_value)
        elif second_arg == "min":
            self.min(thr_value)
        else:
            bot.reply_to(self.message, "Неизвестный второй аргумент, см. /threshold help")

    def main(self, thr_value):
        self.pre_vote(thr_value, "threshold")

    def ban(self, thr_value):
        self.pre_vote(thr_value, "threshold_ban")

    def min(self, thr_value):
        if not data.debug:
            self.current_timer = 86400
        self.pre_vote(thr_value, "threshold_min")

    def pre_vote(self, thr_value, vote_type):

        self.unique_id = vote_type

        if self.is_voting_exist():
            return

        if vote_type == "threshold_min":
            vote_type_text = "минимального порога голосов"
        elif vote_type == "threshold_ban":
            vote_type_text = "порога голосов бан-голосований"
        else:
            vote_type_text = "порога голосов стандартных голосований"

        if 0 < thr_value < data.thresholds_get(minimum=True) and vote_type != "threshold_min":
            bot.reply_to(self.message, f"Количество голосов не может быть ниже текущего "
                                       f"минимального порога {data.thresholds_get(minimum=True)}")
            return

        if thr_value == data.thresholds_get(vote_type == "threshold_ban", vote_type == "threshold_min"):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if data.is_thresholds_auto(vote_type == "threshold_ban", vote_type == "threshold_min") and thr_value == 0:
            bot.reply_to(self.message, "Значения порога уже вычисляются автоматически!")
            return

        warn = ''
        if vote_type == "threshold_min":
            warn = ("\n<b>Внимание! Результаты голосования за минимальный порог принимаются, "
                    "даже если голосование набрало количество голосов ниже текущего минимального порога!\n"
                    "Время завершения голосования за минимальный порог - 24 часа!</b>")

        if thr_value != 0:
            self.vote_text = (f"Тема голосования: установка {vote_type_text} на значение {thr_value}.\n"
                              f"Инициатор голосования: {username_parser(self.message, True)}." + warn)
        else:
            self.vote_text = (f"Тема голосования: установка {vote_type_text} на автоматически выставляемое значение.\n"
                              f"Инициатор голосования: {username_parser(self.message, True)}." + warn)
        self.vote_args = [thr_value, self.unique_id]
        self.poll_maker()
