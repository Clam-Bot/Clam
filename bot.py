import discord
from discord.ext import commands
import coloredlogs, logging
import yaml

# Colored logs install
l = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG', logger=l, fmt='(%(asctime)s) %(levelname)s %(message)s', datefmt='%m/%d/%y - %H:%M:%S %Z')

#Config.yml load
with open("config.yml", 'r') as config:
    try:
        data = yaml.safe_load(config)

    except yaml.YAMLError as exc:
        l.critical("Could not load config.yml")
        print(exc)
        import sys
        sys.exit()

TOKEN = data['bot-token']
description = """
General purpose Discord bot.
"""

class Robonater(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix = "robo.", description = description, activity = discord.Activity(name = "for robo.help for help", type = 3))

        self.remove_command('help')
    
    # I HAVE NO IDEA WHAT IM DOINGGGG

bot = Robonater()
#bot.remove_command('help')

@commands.command(name='ping', description='The ping command', aliases=['p', 'hello', 'hi'])
async def ping(ctx):
    await ctx.send("Pong!")

@commands.command(name='test', description='The test command', aliases=['t'])
async def test(ctx):
    await ctx.send("Hello, {}".format(ctx.author.mention))

@commands.command(name='help', description='The help command', aliases=['help', 'nater', 'h', 'info'])
async def help(ctx):
    help_commands = """
    `{0}.help` - Help command
    `{0}.ping` - Ping command
    `{0}.test` - Test command
    """.format("robo.")
    em = discord.Embed(title = "Robo.nater Help Menu", description = help_commands)
    await ctx.send(embed = em)

bot.add_command(ping)
bot.add_command(test)
bot.add_command(help)

@bot.event
async def on_ready():
    l.info("Logged in as {}".format(bot.user.name))

bot.run(TOKEN)