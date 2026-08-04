import configparser
import logging
import os
import sys
import threading
import time
import traceback
from importlib import reload

import telebot

# Bound by teleboss.shared.runtime after singleton construction.
# ConfigData methods historically resolve bot/sqlWorker as module globals.
bot = None
sqlWorker = None


def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):

    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.error("UNEXPECTED RUNTIME EXCEPTION", exc_info=(exc_type, exc_value, exc_traceback))


def log_thread_exceptions(args):

    thread_name = args.thread.name if args.thread else "Unknown Thread"

    logging.error(
        f"UNEXPECTED EXCEPTION IN THREAD '{thread_name}'",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )


class ConfigData:
    __ADMIN_RECOMMENDED = {"can_change_info": False,
                           # "can_post_messages": None,
                           # "can_edit_messages": None,
                           "can_delete_messages": False,
                           "can_invite_users": True,
                           "can_restrict_members": False,
                           "can_pin_messages": True,
                           "can_promote_members": False,
                           "is_anonymous": False,
                           "can_manage_video_chats": True,
                           # "can_manage_voice_chats": None,
                           "can_manage_topics": True,
                           "can_post_stories": True,
                           "can_edit_stories": False,
                           "can_delete_stories": False}

    __ADMIN_RUS = {"can_change_info": "Изменения профиля группы",
                   # "can_post_messages": None,
                   # "can_edit_messages": None,
                   "can_delete_messages": "Удаление сообщений",
                   "can_invite_users": "Пригласительные ссылки",
                   "can_restrict_members": "Блокировка пользователей",
                   "can_pin_messages": "Закрепление сообщений",
                   "can_promote_members": "Добавление администраторов",
                   "is_anonymous": "Анонимность",
                   "can_manage_video_chats": "Управление видеочатами",
                   # "can_manage_voice_chats": None,
                   "can_manage_topics": "Управление темами",
                   "can_post_stories": "Публикация историй",
                   "can_edit_stories": "Изменение чужих историй",
                   "can_delete_stories": "Удаление чужих историй"}

    # Do not edit this section to change the parameters of the bot!
    # TeleBOSS is customizable via config file or chat voting!
    # It is possible to access sqlWorker.params directly for parameters that are stored in the database
    VERSION = "3.3.2"  # Current bot version
    CODENAME = "Deuterium Discharge"
    MIN_VERSION = "3.3"  # The minimum version from which you can upgrade to this one without breaking the bot
    BUILD_DATE = "02.08.2026"  # Bot build date
    ANONYMOUS_ID = 1087968824  # ID value for anonymous user tg
    EASTER_LINK = "https://2girls.1cup.one"  # Link for Easter eggs
    global_timer = 3600  # Value in seconds of duration of votes
    global_timer_ban = 300  # Value in seconds of duration of ban-votes
    __votes_need = 0  # Required number of votes for early voting closure
    __votes_need_ban = 0  # Required number of votes for early ban-voting closure
    __votes_need_min = 2  # Minimum amount of votes for a vote to be accepted
    main_chat_id = ""  # Outside param/Bot Managed Chat ID
    debug = False  # Debug mode with special presets and lack of saving parameters in the database
    vote_mode = 3  # Sets the mode in which the voice cannot be canceled and transferred (1),
    # it cannot be canceled, but it can be transferred (2) and it can be canceled and transferred (3)
    vote_privacy = 'private'  # Can have values "public", "private" and "hidden", see /votes help for details
    marmalade = True # Enable or disable chat protection mechanism Marmalade
    marmalade_timer = 64800 # The time during which the user will not be able to enter the main chat from the allied
    # one without passing the verification
    marmalade_reset_timer = 604800 # Time after which the entry in the database for the Marmalade protection mechanism
    # becomes irrelevant and requires updating
    wait_timer = 30  # Cooldown before being able to change or cancel voice
    kill_mode = 2  # Mode 0 - the /kill command is disabled, mode 1 - everyone can use it, mode 2 - only chat admins
    fixed_rules = False  # Outside param/If enabled, the presence and absence of rules is decided by the bot host
    rate = True  # Enables or disables the rating system
    admin_fixed = False  # Outside param/If enabled, chat participants
    # cannot change the admin rights allowed for issuance by voting
    admin_allowed = __ADMIN_RECOMMENDED  # Admin rights allowed for issuance in the chat
    path = ""  # Outside param/Path to the chat data folder
    token = ""  # Outside param/Bot token
    chat_mode = "mixed"  # Outside param
    # Private - the chat is protected with a whitelist
    # Mixed - the protection mode is changed by voting in the chat
    # Public - the chat is protected by rapid voting after the participant enters the chat
    # Captcha - chat is protected by a standard captcha
    binary_chat_mode = 0  # Chat protection mode in binary form
    bot_id = None  # Telegram bot account ID
    welcome_default = "Welcome to {1}!"  # Default chat greeting
    # Can be changed in the welcome.txt file, for example "{0}, welcome to {1}",
    # where {0} is the user's nickname, {1} is the name of the chat
    thread_id = None  # Default topic ID in Telegram chat
    SQL_INIT = {"version": VERSION,
                "votes": __votes_need,
                "votes_ban": __votes_need_ban,
                "timer": global_timer,
                "timer_ban": global_timer_ban,
                "min_vote": __votes_need_min,
                "vote_mode": vote_mode,  # Now taken from config.ini
                "wait_timer": wait_timer,  # Now taken from config.ini
                "kill_mode": kill_mode,  # Now taken from config.ini
                "rate": rate,  # It seems that this parameter is not used anywhere?
                "public_mode": binary_chat_mode,
                "allowed_admins": __ADMIN_RECOMMENDED,
                "vote_privacy": vote_privacy,
                "marmalade": marmalade}
    __plugins = {}

    def __init__(self):

        try:
            self.path = sys.argv[1] + "/"
            if not os.path.isdir(sys.argv[1]):
                print("WARNING: working path IS NOT EXIST. Remake.")
                os.mkdir(sys.argv[1])
        except IndexError:
            pass
        except IOError:
            traceback.print_exc()
            print("ERROR: Failed to create working directory! Bot will be closed!")
            sys.exit(1)

        reload(logging)
        logging.basicConfig(
            handlers=[
                logging.FileHandler(self.path + "logging.log", 'w', 'utf-8'),
                logging.StreamHandler(sys.stdout)
            ],
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s',
            datefmt="%d-%m-%Y %H:%M:%S")

        sys.excepthook = log_uncaught_exceptions
        threading.excepthook = log_thread_exceptions

        if not os.path.isfile(self.path + "config.ini"):
            print("Config file isn't found! Trying to remake!")
            self.remake_conf()

        config = configparser.ConfigParser()
        while True:
            try:
                config.read(self.path + "config.ini")
                self.token = config["Chat"]["token"]
                self.vote_mode = int(config["Chat"]["votes-mode"])
                self.wait_timer = int(config["Chat"]["wait-timer"])
                self.kill_mode = int(config["Chat"]["kill-mode"])
                self.fixed_rules = self.bool_init(config["Chat"]["fixed-rules"])
                self.rate = self.bool_init(config["Chat"]["rate"])
                self.admin_fixed = self.bool_init(config["Chat"]["admin-fixed"])
                self.chat_mode = config["Chat"]["chat-mode"]
                if config["Chat"]["chat-id"] != "init":
                    self.main_chat_id = int(config["Chat"]["chat-id"])
                else:
                    self.debug = True
                    self.main_chat_id = -1
                if self.admin_fixed:
                    admin_allowed = {}
                    for name in self.__ADMIN_RECOMMENDED.keys():
                        admin_allowed.update({
                            name: self.bool_init(config["Admin-rules"][name.replace("_", "-")])
                        })
                    self.admin_allowed = admin_allowed
                break
            except Exception as e:
                logging.error((str(e)))
                logging.error(traceback.format_exc())
                time.sleep(1)
                print("\nInvalid config file! Trying to remake!")
                agreement = "-1"
                while agreement != "y" and agreement != "n" and agreement != "":
                    agreement = input("Do you want to reset your broken config file on defaults? (Y/n): ")
                    agreement = agreement.lower()
                if agreement == "" or agreement == "y":
                    self.remake_conf()
                else:
                    sys.exit(0)

        if self.chat_mode not in ["private", "mixed", "public", "captcha"]:
            self.chat_mode = "mixed"
            logging.warning(f"Incorrect chat-mode value, reset to default (mixed)")

        if self.chat_mode == "private":
            self.binary_chat_mode = 0
        elif self.chat_mode == "public":
            self.binary_chat_mode = 1
        elif self.chat_mode == "captcha":
            self.binary_chat_mode = 2

        try:
            self.debug = self.bool_init(config["Chat"]["debug"])
        except (KeyError, TypeError):
            pass

        try:
            self.thread_id = int(config["Chat"]["thread-id"])
        except (KeyError, TypeError, ValueError):
            pass

        if self.debug:
            self.wait_timer = 0

    def sql_worker_get(self):
        self.__votes_need = sqlWorker.params("votes")  # Обращение к глобальной переменной((((
        self.__votes_need_ban = sqlWorker.params("votes_ban")
        self.__votes_need_min = sqlWorker.params("min_vote")
        self.global_timer = sqlWorker.params("timer")
        self.global_timer_ban = sqlWorker.params("timer_ban")
        self.vote_privacy = sqlWorker.params("vote_privacy")
        if self.chat_mode == "mixed":
            self.binary_chat_mode = sqlWorker.params("public_mode")

        if self.debug:
            self.global_timer = 20
            self.global_timer_ban = 10
            self.__votes_need = 2
            self.__votes_need_ban = 2
            self.__votes_need_min = 1

    @staticmethod
    def bool_init(var):
        if var.lower() in ("false", "0"):
            return False
        elif var.lower() in ("true", "1"):
            return True
        else:
            raise TypeError

    def auto_thresholds_get(self, ban=False, minimum=False):

        try:
            member_count = bot.get_chat_members_count(self.main_chat_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(e)
            member_count = 2

        if ban:
            if member_count > 15:
                votes_need_ban = 5
            elif member_count > 5:
                votes_need_ban = 3
            else:
                votes_need_ban = 2
            if votes_need_ban < self.__votes_need_min:
                return self.__votes_need_min
            return votes_need_ban

        elif minimum:
            if member_count > 30:
                min_value = 5
            elif member_count > 15:
                min_value = 3
            else:
                min_value = 2
            if self.__votes_need < min_value:
                self.__votes_need = min_value
            if self.__votes_need_ban < min_value:
                self.__votes_need_ban = min_value
            return min_value
        else:
            votes_need = member_count // 2
            if votes_need < self.__votes_need_min:
                return self.__votes_need_min
            if votes_need > 7:
                return 7
            if votes_need <= 1:
                return 2
            return votes_need

    def thresholds_get(self, ban=False, minimum=False):
        if ban:
            if self.__votes_need_ban != 0:
                return self.__votes_need_ban
            else:
                return self.auto_thresholds_get(ban)
        elif minimum:
            if self.__votes_need_min != 0:
                return self.__votes_need_min
            else:
                return self.auto_thresholds_get(False, minimum)
        else:
            if self.__votes_need != 0:
                return self.__votes_need
            else:
                return self.auto_thresholds_get()

    def is_thresholds_auto(self, ban=False, minimum=False):
        if ban:
            if not self.__votes_need_ban:
                return True
            return False
        elif minimum:
            if not self.__votes_need_min:
                return True
            return False
        else:
            if not self.__votes_need:
                return True
            return False

    def thresholds_set(self, value, ban=False, minimum=False):
        if ban:
            self.__votes_need_ban = value
            if not self.debug:
                sqlWorker.params("votes_ban", value)
        elif minimum:
            self.__votes_need_min = value
            if self.__votes_need_ban < self.thresholds_get(False, True) and self.__votes_need_ban:
                self.__votes_need_ban = value
            if self.__votes_need < self.thresholds_get(False, True) and self.__votes_need:
                self.__votes_need = value
            if not self.debug:
                sqlWorker.params("min_vote", value)
        else:
            self.__votes_need = value
            if not self.debug:
                sqlWorker.params("votes", value)

    def timer_set(self, value, ban=False):
        if ban:
            self.global_timer_ban = value
            if not self.debug:
                sqlWorker.params("timer_ban", value)
        else:
            self.global_timer = value
            if not self.debug:
                sqlWorker.params("timer", value)

    def remake_conf(self):
        token, chat_id = "", ""
        while token == "":
            token = input("Please, write your bot token: ")
        while chat_id == "":
            chat_id = input('Please enter ID of your chat or "init" to enter initialization mode: ')
        config = configparser.ConfigParser()
        config.add_section("Chat")
        config.set("Chat", "token", token)
        config.set("Chat", "chat-id", chat_id)
        config.set("Chat", "votes-mode", "3")
        config.set("Chat", "wait-timer", "30")
        config.set("Chat", "kill-mode", "2")
        config.set("Chat", "fixed-rules", "false")
        config.set("Chat", "rate", "true")
        config.set("Chat", "admin-fixed", "false")
        config.set("Chat", "chat-mode", "mixed")
        config.set("Chat", "thread-id", "none")
        config.add_section("Admin-rules")
        for name, value in self.__ADMIN_RECOMMENDED.items():
            config.set("Admin-rules", name.replace("_", "-"), str(value).lower())
        try:
            with open(self.path + "config.ini", "w") as config_file:
                config.write(config_file)
            print("New config file was created successful")
        except IOError:
            print("ERR: Bot cannot write new config file and will close")
            logging.error(traceback.format_exc())
            sys.exit(1)

    @property
    def plugins(self):
        return self.__plugins

    @plugins.setter
    def plugins(self, value):
        if not isinstance(value, dict):
            return
        self.__plugins = value

    @property
    def admin_rus(self):
        return self.__ADMIN_RUS
