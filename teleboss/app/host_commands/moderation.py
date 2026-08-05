"""Moderation host command handlers."""

import logging
import time

import telebot

from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.parsers import (
    extract_arg,
    formatted_timer,
    reply_msg_target,
    time_parser,
    topic_reply_fix,
    username_parser,
)
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.engine import poll_engine


class ModerationMixin:
    """Mixin providing moderation host commands."""

    @staticmethod
    def mute_user(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if data.kill_mode == 0:
            bot.reply_to(message, "Команда /kill отключена в файле конфигурации бота.")
            return

        if topic_reply_fix(message.reply_to_message) is None:

            if data.kill_mode == 2:
                only_for_admins = "\nВ текущем режиме команду могут применять только администраторы чата."
            else:
                only_for_admins = ""

            bot.reply_to(message, "Ответьте на сообщение пользователя, которого необходимо отправить в мут.\n"
                         + "ВНИМАНИЕ: использовать только в крайних случаях - во избежание злоупотреблений "
                         + "вы так же будете лишены прав на тот же срок.\n"
                         + "Даже если у вас есть права админа, вы будете их автоматически лишены, "
                         + "если они были выданы с помощью бота." + only_for_admins)
            return

        if data.bot_id == message.reply_to_message.from_user.id:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if data.ANONYMOUS_ID in [message.reply_to_message.from_user.id, message.from_user.id]:
            bot.reply_to(message, "Я не могу ограничить анонимного пользователя!")
            return

        if message.from_user.id != message.reply_to_message.from_user.id and data.kill_mode == 2:
            if bot.get_chat_member(data.main_chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "В текущем режиме команду могут применять только администраторы чата.")
                return

        if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
            bot.reply_to(message, "Он и так в муте, не увеличивайте его страдания.")
            return

        if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status in ("kicked", "left"):
            bot.reply_to(message, "Данный пользователь не состоит в чате.")
            return

        timer_mute = 3600
        if extract_arg(message.text, 1) is not None:
            timer_mute = time_parser(extract_arg(message.text, 1))
            if timer_mute is None:
                bot.reply_to(message, "Неправильный аргумент, укажите время мута от 31 секунды до 12 часов.")
                return

        if not 30 < timer_mute <= 43200:
            bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 12 часов.")
            return

        try:
            abuse_vote_timer = int(poll_engine.vote_abuse.get("abuse" + str(message.from_user.id)))
        except TypeError:
            abuse_vote_timer = 0

        if abuse_vote_timer + 10 > int(time.time()):
            return

        poll_engine.vote_abuse.update({"abuse" + str(message.from_user.id): int(time.time())})

        try:
            bot.restrict_chat_member(data.main_chat_id, message.reply_to_message.from_user.id,
                                     until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
            if message.from_user.id == message.reply_to_message.from_user.id:
                if data.rate:
                    sqlWorker.update_rate(message.from_user.id, -3)
                    bot.reply_to(message, f"Пользователь {username_parser(message)}"
                                 + f" решил отдохнуть от чата на {formatted_timer(timer_mute)}"
                                 + " и снизить себе рейтинг на 3 пункта.")
                else:
                    bot.reply_to(message, f"Пользователь {username_parser(message)}"
                                 + f" решил отдохнуть от чата на {formatted_timer(timer_mute)}")
                return
            if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                    and data.rate:
                sqlWorker.update_rate(message.reply_to_message.from_user.id, -5)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error restricting attacked user with /kill command!\n{e}')
            bot.reply_to(message, "Я не смог снять права данного пользователя. Не имею права.")
            return

        try:
            bot.restrict_chat_member(data.main_chat_id, message.from_user.id,
                                     until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
            if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                    and data.rate:
                sqlWorker.update_rate(message.from_user.id, -5)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error restricting initiator user with /kill command!\n{e}')
            bot.reply_to(message, "Я смог снять права данного пользователя на "
                         + formatted_timer(timer_mute) + ", но не смог снять права автора заявки.")
            return

        user_rate = ""
        if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                and data.rate:
            user_rate = "\nРейтинг обоих пользователей снижен на 5 пунктов."

        bot.reply_to(message, f"<b>Обоюдоострый Меч сработал</b>.\nТеперь {username_parser(message, True)} "
                              f"и {username_parser(message.reply_to_message, True)} "
                              f"будут дружно молчать в течении " + formatted_timer(timer_mute) + user_rate,
                     parse_mode="html")


    @staticmethod
    def pardon(message):
        if not bot_name_checker(message):
            return

        if message.chat.id == data.main_chat_id:
            if bot.get_chat_member(data.main_chat_id, message.from_user.id).status not in ("administrator", "creator"):
                bot.reply_to(message, "Данная команда не может быть запущена в основном чате не администраторами.")
            elif topic_reply_fix(message.reply_to_message) is None:
                bot.reply_to(message, "Требуется реплейнуть сообщение участника, "
                                      "которому вы хотите сбросить абуз инвайта.")
            elif message.reply_to_message.from_user.id == data.bot_id:
                bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            else:
                user_id, username, _ = reply_msg_target(message.reply_to_message)
                sqlWorker.abuse_remove(user_id)
                bot.reply_to(message, f"Абуз инвайта для {username} сброшен!")
                return
        elif data.debug:
            sqlWorker.abuse_remove(message.chat.id)
            target = "инвайт" if message.chat.id == message.from_user.id else "добавление в союзники"
            user = "пользователя" if message.chat.id == message.from_user.id else "чата"
            bot.reply_to(message, f"Абуз заявки на {target} сброшен для текущего {user}.")
            return
        else:
            bot.reply_to(message, "Данная команда не может быть запущена в обычном режиме вне основного чата.")


    @staticmethod
    def revoke(message):
        if not bot_name_checker(message):
            return

        is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
        if not is_allies:
            if command_forbidden(message, text="Данную команду можно запустить только "
                                                     "в основном чате или в союзных чатах."):
                return

        try:
            bot.revoke_chat_invite_link(data.main_chat_id, bot.get_chat(data.main_chat_id).invite_link)
            bot.reply_to(message, "Пригласительная ссылка на основной чат успешно сброшена.")
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error resetting invitation link!\n{e}')
            bot.reply_to(message, "Ошибка сброса основной пригласительной ссылки! Подробная информация в логах бота.")


    @staticmethod
    def cremate(message):
        if not bot_name_checker(message) or command_forbidden(message):
            return

        if topic_reply_fix(message.reply_to_message):
            user_id = message.reply_to_message.from_user.id
        elif extract_arg(message.text, 1) is not None:
            try:
                user_id = int(extract_arg(message.text, 1))
            except ValueError:
                bot.reply_to(message, "Указан неверный User ID.")
                return
        else:
            bot.reply_to(message, "Требуется реплейнуть сообщение удалённого аккаунта "
                                  "или ввести ID аккаунта аргументом команды.")
            return

        if user_id == data.bot_id:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        try:
            first_name = bot.get_chat_member(data.main_chat_id, user_id).user.first_name
        except telebot.apihelper.ApiTelegramException as e:
            if "invalid user_id specified" in str(e):
                bot.reply_to(message, "Указан неверный User ID.")
            else:
                logging.error(f'Error getting account information when trying to cremate!\n{e}')
                bot.reply_to(message, "Неизвестная ошибка Telegram API. Информация сохранена в логи бота.")
            return

        if bot.get_chat_member(data.main_chat_id, user_id).status in ('left', 'kicked'):
            bot.reply_to(message, "Данный участник не находится в чате.")
        elif first_name == '':
            try:
                bot.ban_chat_member(data.main_chat_id, user_id, int(time.time()) + 60)
                bot.reply_to(message, "Удалённый аккаунт успешно кремирован.")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Account cremation error!\n{e}')
                bot.reply_to(message, "Ошибка кремации удалённого аккаунта. Недостаточно прав?")
        else:
            bot.reply_to(message, "Данный участник не является удалённым аккаунтом.")
