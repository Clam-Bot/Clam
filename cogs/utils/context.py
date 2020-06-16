from discord.ext import commands, menus
import discord

import enum

from .emojis import GREEN_TICK, RED_TICK
from .menus import MenuPages


class Confirm(menus.Menu):
    def __init__(self, msg):
        super().__init__(timeout=30.0, delete_message_after=True)
        self.msg = msg
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return await channel.send(self.msg)

    @menus.button(GREEN_TICK)
    async def do_confirm(self, payload):
        self.result = True
        self.stop()

    @menus.button(RED_TICK)
    async def do_deny(self, payload):
        self.result = False
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class BasicPageSource(menus.ListPageSource):
    def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        return "\n".join(f"`{i+1}.` {v}" for i, v in enumerate(entries, start=offset))


class BasicPages(MenuPages):
    def __init__(self, entries, *args, **kwargs):
        super().__init__(
            BasicPageSource(entries, per_page=10), clear_reactions_after=True
        )


class Context(commands.Context):
    @property
    def guild_prefix(self):
        return self.bot.guild_prefix(self.guild)

    @property
    def console(self):
        return self.bot.console

    @property
    def db(self):
        return self.bot.pool

    def tick(self, tick):
        tick = bool(tick)
        ticks = {True: GREEN_TICK, False: RED_TICK}
        return ticks[tick]

    async def confirm(self, message):
        return await Confirm(message).prompt(self)

    def pages(self, entries):
        return BasicPages(entries)
