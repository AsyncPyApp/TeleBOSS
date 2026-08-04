from teleboss.domain.moderation.prevote import NewUserChecker
from teleboss.shared.runtime import bot


@bot.message_handler(content_types=['new_chat_members'])
def new_usr_checker(message):
    NewUserChecker(message)
