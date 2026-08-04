"""Sole construction site for shared runtime singletons."""
import telebot

from teleboss.shared import config as config_mod
from teleboss.shared.config import ConfigData
from teleboss.shared.help_ui import Helper
from teleboss.shared.storage.sql_worker import SqlWorker

data = ConfigData()
helper = Helper()
bot = telebot.TeleBot(data.token)
sqlWorker = SqlWorker(data.path + "database.db", data.SQL_INIT)

# Preserve ConfigData bare-name resolution for bot/sqlWorker (historical utils globals).
config_mod.bot = bot
config_mod.sqlWorker = sqlWorker
