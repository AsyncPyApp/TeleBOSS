import time
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    time_parser,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.bases import PreVote

class Shield(PreVote):
    vote_type = "shield"
    unique_id = vote_type
    help_text = 'Эта команда включает режим защиты чата - Раскрытый Зонтик. В этом режиме бот блокирует входящих ' \
                'пользователей при попытке входа из союзного чата и напрямую, а так же ботов при попытке их ' \
                'добавить. В режиме чата "приватный" войти в чат всё ещё будет возможно по вайтлисту.\n' \
                'Аргумент "force", доступный только администраторам, позволит включить режим защиты чата на срок от ' \
                '1 до 24 часов, по умолчанию на 12 часов. Аргумент "enable" и "disable" позволит голосованием ' \
                'включить (обновить таймер) и отключить режим защиты чата на срок от 1 часа до 30 дней.\n' \
                'В режиме защиты бот удаляет сообщение о входе пользователя, не оставляя следов при флуд-атаке.\n'

    pre_return = PreVote.pre_return_command_forbidden

    def help(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            status = "<b>Текущий статус защиты</b>: отключена."
        else:
            status = f"<b>Текущий статус защиты</b>: включена.\n<b>До отключения осталось:</b> " \
                     f"{formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text + status, parse_mode="html")

    def direct_fn(self):
        self.help()

    def set_args(self) -> dict:
        return {"force": self.force, "enable": self.enable, "disable": self.disable}

    def force(self):
        if not bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("creator", "administrator"):
            bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
            return
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            bot.reply_to(self.message, "Защита уже включена! До отключения осталось "
                                       f"{formatted_timer(shield_timer - int(time.time()))}")
            return
        timer = time_parser(extract_arg(self.msg_txt, 2))
        if timer is None:
            timer = 43200
        if not 3600 <= timer <= 86400:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 до 24 часов!")
            return
        sqlWorker.params("shield", rewrite_value=int(time.time()) + timer)
        bot.reply_to(self.message, f"Защита чата успешно включена на {formatted_timer(timer)} "
                                   "Теперь добавление новых участников временно невозможно!")

    def enable(self):
        timer = extract_arg(self.msg_txt, 2)
        if not timer:
            bot.reply_to(self.message, "Требуется указать третьим аргументом значение таймера защиты "
                                       "(от 1 часа до 30 дней)")
            return
        timer = time_parser(timer)
        if timer is None:
            bot.reply_to(self.message, "Не удалось распарсить аргумент таймера.")
            return
        if not 3600 <= timer <= 2592000:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 часа до 30 дней!")
            return
        self.create_vote("включение/обновление таймера", timer)

    def disable(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            bot.reply_to(self.message, "Защита чата уже отключена!")
            return
        self.create_vote("отключение", 0)

    def create_vote(self, vote_type, timer):
        if self.is_voting_exist():
            return
        timer_text = "." if timer == 0 else f" на {formatted_timer(timer)}"
        self.vote_text = (f"Тема голосования: {vote_type} режима защиты чата от атак{timer_text}\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(vote_args=[timer, username_parser(self.message, True)])

class Marmalade(PreVote):
    vote_type = "marmalade"
    unique_id = vote_type
    help_text = ("Marmalade - механизм защиты чата от проникновения новых пользователей через союзные чаты.\n"
                 "Когда кто-то заходит в союзный чат, бот запоминает его, если данного человека нет в основном чате. "
                 "Если данный человек попробует зайти в основной чат раньше, чем через 18 часов после этого, ему "
                 "потребуется пройти стандартную процедуру голосования для вступления (внутри чата) или капчу, в "
                 "зависимости от настроек приватности чата. Если прошло более 18 часов или бот не зафиксировал "
                 "вступление в союзный чат, то человек может войти без каких-либо проверок. Запись в БД актуальна в "
                 "течении недели. Если по истечении этого времени человек перезашёл в союзный чат, то запись "
                 "обновляется. Вы можете включить и выключить Marmalade с помощью голосования, однако настоятельно "
                 "рекомендуется оставить его включённым (по умолчанию).\n")

    pre_return = PreVote.pre_return_command_forbidden

    def help(self):
        marmalade = sqlWorker.params("marmalade", default_return=True)
        marmalade_text = "включена" if marmalade else "отключена"
        status = f"<b>Текущий статус защиты</b>: {marmalade_text}."
        bot.reply_to(self.message, self.help_text + status, parse_mode="html")

    def direct_fn(self):
        self.help()

    def set_args(self) -> dict:
        return {"enable": self.enable, "disable": self.disable}

    def enable(self):
        if sqlWorker.params("marmalade", default_return=True):
            bot.reply_to(self.message, "Защита чата Marmalade уже включена!")
            return
        self.create_vote(True)

    def disable(self):
        if not sqlWorker.params("marmalade", default_return=True):
            bot.reply_to(self.message, "Защита чата Marmalade уже отключена!")
            return
        self.create_vote(False)

    def create_vote(self, marmalade_bool):
        if self.is_voting_exist():
            return
        marmalade_text = "включение" if marmalade_bool else "отключение"
        self.vote_text = (f"Тема голосования: {marmalade_text} механизма защиты чата Marmalade\n"
                          f"Инициатор голосования: {username_parser(self.message, True)}.")
        self.poll_maker(vote_args=[marmalade_bool, username_parser(self.message, True)])
