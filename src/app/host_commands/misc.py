"""Miscellaneous host command handlers."""

import logging
import multiprocessing
import queue
import random
import time

import telebot

from teleboss.shared.access import bot_name_checker, command_forbidden
from teleboss.shared.calc import calc_engine
from teleboss.shared.parsers import extract_arg
from teleboss.shared.runtime import bot, data, sqlWorker
from teleboss.voting.engine import poll_engine


class MiscMixin:
    """Mixin providing miscellaneous host commands."""

    @staticmethod
    def mail(message):
        if not bot_name_checker(message):
            return

        if message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(message, "Вы не можете подписаться на рассылку, так как являетесь анонимным администратором.")
            return

        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("kicked", "left"):
            bot.reply_to(message, "Вы не можете подписаться на рассылку, если не состоите в чате.")
            return

        if extract_arg(message.text, 1) == "status":
            subscribed = " " if sqlWorker.mailing(message.from_user.id) else " не "
            bot.reply_to(message, f"Вы{subscribed}подписаны на рассылку и{subscribed}получаете информацию о новых "
                                  f"голосованиях в чате.\n<b>Обратите внимание, что если боту будет запрещено писать "
                                  "вам в личные сообщения, рассылка отключится автоматически!\n"
                                  "Переключить статус рассылки можно командой /mail.</b>",
                         parse_mode='html')
            return

        if sqlWorker.mailing(message.from_user.id):
            sqlWorker.mailing(message.from_user.id, remove=True)
            subscribed = "отключили"
        else:
            sqlWorker.mailing(message.from_user.id, add=True)
            subscribed = "подключили"
        bot.reply_to(message, f"Вы {subscribed} рассылку о новых голосованиях в личных сообщениях бота.")


    @staticmethod
    def random_msg(message):
        if not bot_name_checker(message):
            return

        try:
            abuse_vote_timer = int(poll_engine.vote_abuse.get("random"))
        except TypeError:
            abuse_vote_timer = 0

        abuse_random = sqlWorker.abuse_random(message.chat.id)

        if abuse_vote_timer + abuse_random > int(time.time()) or abuse_random < 0:
            return

        poll_engine.vote_abuse.update({"random": int(time.time())})

        msg_id = ""
        for i in range(5):
            try:
                msg_id = random.randint(1, message.id)
                bot.forward_message(message.chat.id, message.chat.id, msg_id,
                                    message_thread_id=message.message_thread_id)
                return
            except telebot.apihelper.ApiTelegramException as e:
                if "message has protected content and can't be forwarded" in str(e):
                    bot.reply_to(message, "Пересылка рандомных сообщений невозможна, чат защищён от копирования.")
                    return
                elif i == 4:
                    logging.error(f'Error forwarding random message with number {msg_id} '
                                  f'in chat {message.chat.id}!\n{e}')
                    bot.reply_to(message, f"Ошибка взятия рандомного сообщения с номером {msg_id}!")


    @staticmethod
    def calc(message):
        if not bot_name_checker(message):
            return

        is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
        user_status = bot.get_chat_member(data.main_chat_id, message.from_user.id).status
        if not (is_allies or user_status in ("creator", "administrator", "member")):
            if command_forbidden(message, text="Данную команду можно запустить только в основном чате, "
                                                     "участникам основного чата или в союзных чатах."):
                return

        if extract_arg(message.text, 1) is None:
            bot.reply_to(message, "Данная команда не может быть запущена без аргумента.")
            return

        calc_text = message.text.split(maxsplit=1)[1]
        if len(calc_text.replace(" ", "")) > 500:
            bot.reply_to(message, "В выражении должно быть не более 500 полезных символов.")
            return
        if not set(calc_text).issubset("1234567890 */+-().,^"):
            bot.reply_to(message, "Неверно введено выражение для вычисления.")
            return

        to_send = multiprocessing.Queue()
        process = multiprocessing.Process(target=calc_engine, args=(calc_text, to_send))
        process.start()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            bot.reply_to(message, "Время вычисления превысило таймаут. Отменено.")
            return

        try:
            calc_result = to_send.get(timeout=5)
        except queue.Empty:
            bot.reply_to(message, "Неизвестная ошибка вычисления! Информация сохранена в логи бота.")
            return

        try:
            bot.reply_to(message, calc_result, parse_mode='html')
        except telebot.apihelper.ApiTelegramException as e:
            if 'message is too long' in str(e):
                bot.reply_to(message, "Результат слишком большой для отправки.")


    @staticmethod
    def niko(message):
        if not bot_name_checker(message):
            return

        try:
            bot.send_sticker(message.chat.id, random.choice(bot.get_sticker_set("OneShotSolstice").stickers).file_id,
                             message_thread_id=message.message_thread_id)
            # bot.send_sticker(message.chat.id, open(os.path.join("ee", random.choice(os.listdir("ee"))), 'rb'))
            # Random file
        except (FileNotFoundError, telebot.apihelper.ApiTelegramException, IndexError):
            pass
