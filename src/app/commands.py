from teleboss.app.host_commands import HostCommands
from teleboss.domain.admin.prevote import (
    Avatar,
    Deop,
    Description,
    OpSetup,
    Rank,
    RemoveTopic,
    Title,
)
from teleboss.domain.allies.prevote import AlliesList
from teleboss.domain.content.prevote import CustomPoll, Rules
from teleboss.domain.moderation.prevote import (
    Ban,
    Invite,
    Kick,
    MessageRemover,
    MessageSilentRemover,
    Mute,
    Unban,
)
from teleboss.domain.settings.prevote import (
    Marmalade,
    PrivateMode,
    Rating,
    Shield,
    Thresholds,
    Timer,
    Votes,
    Whitelist,
)
from teleboss.shared.command import Command


class BuildInCommands(HostCommands):

    def __init__(self):
        self.built_in_commands_dict = {
            'invite': Command(self.add_usr, None),
            'ban': Command(self.ban_usr, ('banuser',)),
            'kick': Command(self.kick_usr, ('kickuser',)),
            'mute': Command(self.mute_usr, None),
            'unmute': Command(self.unban_usr, ('unban',)),
            'threshold': Command(self.thresholds, None),
            'timer': Command(self.timer, None),
            'rate': Command(self.rate, None),
            'whitelist': Command(self.whitelist, None),
            'delete': Command(self.delete_msg, None),
            'clear': Command(self.clear_msg, None),
            'private': Command(self.private_mode, None),
            'op': Command(self.op, None),
            'remtopic': Command(self.rem_topic, None),
            'rank': Command(self.rank, None),
            'deop': Command(self.deop, None),
            'title': Command(self.title, None),
            'description': Command(self.description, None),
            'chatpic': Command(self.chat_pic, None),
            'allies': Command(self.allies_list, None),
            'shield': Command(self.shield, None),
            'rules': Command(self.rules_msg, None),
            'poll': Command(self.custom_poll, None),
            'votes': Command(self.votes, None),
            'marmalade': Command(self.marmalade, None),
            'answer': Command(self.add_answer, None),
            'mail': Command(self.mail, None),
            'status': Command(self.status, None),
            'random': Command(self.random_msg, ('redrum',)),
            'pardon': Command(self.pardon, None),
            'getchat': Command(self.get_id, None),
            'help': Command(self.help_msg, None),
            'kill': Command(self.mute_user, None),
            'revoke': Command(self.revoke, None),
            'cremate': Command(self.cremate, None),
            'calc': Command(self.calc, None),
            'start': Command(self.start, None),
            'overview': Command(self.overview, None),
            'version': Command(self.version, None),
            'plugins': Command(self.plugins, None),
            'git': Command(self.git, None),
            'niko': Command(self.niko, None),
        }

    @staticmethod
    def add_usr(message):
        Invite(message)


    @staticmethod
    def ban_usr(message):
        Ban(message)


    @staticmethod
    def kick_usr(message):
        Kick(message)


    @staticmethod
    def mute_usr(message):
        Mute(message)


    @staticmethod
    def unban_usr(message):
        Unban(message)


    @staticmethod
    def thresholds(message):
        Thresholds(message)


    @staticmethod
    def timer(message):
        Timer(message)


    @staticmethod
    def rate(message):
        Rating(message)


    @staticmethod
    def whitelist(message):
        Whitelist(message)


    @staticmethod
    def delete_msg(message):
        MessageRemover(message)


    @staticmethod
    def clear_msg(message):
        MessageSilentRemover(message)


    @staticmethod
    def private_mode(message):
        PrivateMode(message)


    @staticmethod
    def op(message):
        OpSetup(message)


    @staticmethod
    def rem_topic(message):
        RemoveTopic(message)


    @staticmethod
    def rank(message):
        Rank(message)


    @staticmethod
    def deop(message):
        Deop(message)


    @staticmethod
    def title(message):
        Title(message)


    @staticmethod
    def description(message):
        Description(message)


    @staticmethod
    def chat_pic(message):
        Avatar(message)


    @staticmethod
    def allies_list(message):
        AlliesList(message)


    @staticmethod
    def shield(message):
        Shield(message)


    @staticmethod
    def rules_msg(message):
        Rules(message)


    @staticmethod
    def custom_poll(message):
        CustomPoll(message)


    @staticmethod
    def votes(message):
        Votes(message)


    @staticmethod
    def marmalade(message):
        Marmalade(message)
