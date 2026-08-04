import prevote
from utils import bot


@bot.message_handler(content_types=['new_chat_members'])
def new_usr_checker(message):
    prevote.NewUserChecker(message)
