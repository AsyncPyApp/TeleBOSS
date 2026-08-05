import json
import logging
import sys
import traceback

from telebot import types

from teleboss.shared.parsers import html_fix


class Helper:

    __help_json: dict

    def __init__(self):
        try:
            with open("help.json", encoding='utf-8') as f:
                self.__help_json = json.load(f)
        except (IOError, json.decoder.JSONDecodeError):
            logging.error("Error reading JSON help file! Bot will be closed.")
            logging.error(traceback.format_exc())
            sys.exit(1)

    @property
    def help_json(self):
        return self.__help_json

    def get_main_list(self):
        output = "<b>Выберите категорию команд:</b>\n\n<blockquote expandable>"
        buttons_main_row = []
        buttons_main = []

        for index, category in enumerate(self.help_json['category']):
            buttons_main_row.append(types.InlineKeyboardButton(text=str(index + 1), callback_data=f"help!_cat_{index}"))
            if len(buttons_main_row) > 3:
                buttons_main.append(buttons_main_row)
                buttons_main_row = []
            output += f"<b>{index + 1} - {html_fix(category['name'])}</b>\n"
            commands_text = []
            for command in category['commands']:
                 commands_text.append(f"<code>{html_fix(command['name'])}</code>")
                 if command['aliases']:
                     commands_text.append(f"<code>{html_fix(', '.join(command['aliases']))}</code>")
            output += f'{", ".join(commands_text)}\n'
        if buttons_main_row:
            buttons_main.append(buttons_main_row)
        output += "</blockquote>"
        return output, types.InlineKeyboardMarkup(buttons_main)

    def get_category_list(self, index):
        output = ""
        try:
            category = self.help_json['category'][int(index)]
        except IndexError:
            raise IndexError("Category index not found")
        output += f"<b>{html_fix(category['name'])}</b>\n<blockquote>"
        commands_list = []
        for command in category['commands']:
            command_text = [html_fix(f"/{command['name']}")]
            if command['aliases']:
                command_text.append(f'/{html_fix("/".join(command["aliases"]))}')
            if command['args']:
                command_text.append("[" + html_fix("] [".join(command['args'])) + "]")
            if command['mark']:
                command_text.append(html_fix(f"({command['mark']})"))
            commands_list.append(f"{' '.join(command_text)} - {' '.join(command['short_desc'])}")
        output += "{}</blockquote>\n".format('\n'.join(commands_list))
        return output, types.InlineKeyboardMarkup([[types.InlineKeyboardButton(text="На главную",
                                                                               callback_data=f"help!_main")]])
