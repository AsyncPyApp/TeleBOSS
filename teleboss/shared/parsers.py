import time


def extract_arg(text: str, num: int):
    try:
        return text.split()[num]
    except (IndexError, AttributeError):
        return None


def html_fix(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def username_parser(message, html=False):
    if message.from_user.first_name == "":
        return "DELETED USER"

    if message.from_user.username == "GroupAnonymousBot":
        return "ANONYMOUS ADMIN"

    if message.from_user.username is None:
        if message.from_user.last_name is None:
            username = str(message.from_user.first_name)
        else:
            username = str(message.from_user.first_name) + " " + str(message.from_user.last_name)
    else:
        if message.from_user.last_name is None:
            username = str(message.from_user.first_name) + " (@" + str(message.from_user.username) + ")"
        else:
            username = str(message.from_user.first_name) + " " + str(message.from_user.last_name) + \
                       " (@" + str(message.from_user.username) + ")"

    if not html:
        return username

    return html_fix(username)


def username_parser_invite(message, html=False):
    if message.json.get("new_chat_participant").get("username") is None:
        if message.json.get("new_chat_participant").get("last_name") is None:
            username = message.json.get("new_chat_participant").get("first_name")
        else:
            username = message.json.get("new_chat_participant").get("first_name") + " " \
                       + message.json.get("new_chat_participant").get("last_name")
    else:
        if message.json.get("new_chat_participant").get("last_name") is None:
            username = message.json.get("new_chat_participant").get("first_name") \
                       + " (@" + message.json.get("new_chat_participant").get("username") + ")"
        else:
            username = message.json.get("new_chat_participant").get("first_name") + " " \
                       + message.json.get("new_chat_participant").get("last_name") + \
                       " (@" + message.json.get("new_chat_participant").get("username") + ")"

    if not html:
        return username

    return html_fix(username)


def username_parser_chat_member(chat_member, html=False, need_username=True):
    if chat_member.user.username is None or need_username is False:
        if chat_member.user.last_name is None:
            username = chat_member.user.first_name
        else:
            username = chat_member.user.first_name + " " + chat_member.user.last_name
    else:
        if chat_member.user.last_name is None:
            username = chat_member.user.first_name + " (@" + chat_member.user.username + ")"
        else:
            username = chat_member.user.first_name + " " + chat_member.user.last_name + \
                       " (@" + chat_member.user.username + ")"

    if not html:
        return username

    return html_fix(username)


def reply_msg_target(message):
    if message.json.get("new_chat_participant") is not None:
        user_id = message.json.get("new_chat_participant").get("id")
        username = username_parser_invite(message)
        is_bot = message.json.get("new_chat_participant").get("is_bot")
    elif message.left_chat_member is not None:
        user_id = message.left_chat_member.id
        is_bot = message.left_chat_member.is_bot
        message.from_user = message.left_chat_member  # Какие ж смешные костыли))0)))
        username = username_parser(message)
    else:
        user_id = message.from_user.id
        username = username_parser(message)
        is_bot = message.from_user.is_bot

    return user_id, username, is_bot


def time_parser(instr: str):
    tf = {
        "s": lambda x: x,
        "m": lambda x: tf['s'](x) * 60,
        "h": lambda x: tf['m'](x) * 60,
        "d": lambda x: tf['h'](x) * 24,
        "w": lambda x: tf['d'](x) * 7,
    }
    buf = 0
    pdata = 0
    for label in instr:
        if label.isnumeric():
            buf = buf * 10 + int(label)
        else:
            label = label.lower()
            if label in tf:
                pdata += tf[label](buf)
            else:
                return None
            buf = 0
    return pdata + buf


def formatted_timer(timer_in_second):
    if timer_in_second <= 0:
        return "0c."
    elif timer_in_second < 60:
        return time.strftime("%Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 3600:
        return time.strftime("%Mм. и %Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 86400:
        return time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))
    else:
        days = timer_in_second // 86400
        timer_in_second = timer_in_second - days * 86400
        return str(days) + " дн., " + time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))


def topic_reply_fix(message):  # Опять эти конченые из тг мне насрали
    if not message or message.content_type == "forum_topic_created":
        return None
    return message
