from discord.ext import commands, menus
import discord

from datetime import datetime as d
from datetime import timedelta
import re
import os
import base64
import binascii
import humanize
import io
import functools
from PIL import Image
import typing
import dateparser
import asyncio

from .utils import colors, emojis
from .utils.human_time import plural


def snowstamp(snowflake):
    timestamp = (int(snowflake) >> 22) + 1420070400000
    timestamp /= 1000

    return d.utcfromtimestamp(timestamp).strftime("%b %d, %Y at %#I:%M %p")


class GlobalUser(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            if not ctx.guild:
                raise commands.BadArgument()  # blank to skip
            user = await commands.MemberConverter().convert(ctx, arg)

        except commands.BadArgument:
            try:
                user = await commands.UserConverter().convert(ctx, arg)

            except commands.BadArgument:
                try:
                    arg = int(arg)

                except ValueError:
                    arg = discord.utils.escape_mentions(arg)
                    raise commands.BadArgument(
                        f"Could not find a member or user `{arg}` with that name. Try with their ID instead."
                    )
                try:
                    user = await ctx.bot.fetch_user(arg)

                except discord.HTTPException:
                    raise commands.BadArgument(
                        f"Could not find a member or user with the ID of `{arg}`."
                    )

        return user


class SearchPages(menus.ListPageSource):
    def __init__(self, data):
        pages_limit = 10
        current = (
            f"Found **{len(data)}** {'matches' if len(data) > 1 else 'match'}! ```ini\n"
        )
        for i, entry in enumerate(data):
            if entry.nick:
                nick = f"{entry.nick} - "
            else:
                nick = ""
            if (
                len(
                    current
                    + f"\n[{i+1}] {nick}{entry.name}#{entry.discriminator} ({entry.id})"
                )
                <= 2000
            ):
                current += (
                    f"\n[{i+1}] {nick}{entry.name}#{entry.discriminator} ({entry.id})"
                )
            else:
                current = f"Found **{len(data)}** {'matches' if len(data) > 1 else 'match'}! ```ini\n"
                if i + 1 < pages_limit:
                    pages_limit = i + 1
        print(pages_limit)
        super().__init__(data, per_page=pages_limit)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        msg = f"Found **{len(self.entries)}** {'matches' if len(self.entries) > 1 else 'match'}! ```ini\n"
        for i, member in enumerate(entries, start=offset):
            if member.nick:
                nick = f"{member.nick} - "
            else:
                nick = ""
            msg += f"\n[{i+1}] {nick}{member.name}#{member.discriminator} ({member.id})"
        # msg += '\n'.join(f'{i+1}. {v}' for i, v in enumerate(entries, start=offset))
        msg += "\n```"
        return msg


class Tools(commands.Cog):
    """Useful Discord tools."""

    def __init__(self, bot):
        self.bot = bot
        self.emoji = ":tools:"
        self.log = self.bot.log

        if not hasattr(bot, "sniped_messages"):
            self.bot.sniped_messages = []

        self.sniped_messages = self.bot.sniped_messages

    async def prompt(self, ctx, msg, *, timeout=180.0, check=None):
        def default_check(ms):
            return ms.author == ctx.author and not ms.guild

        check = check or default_check

        await ctx.author.send(msg)

        try:
            message = await self.bot.wait_for("message", timeout=timeout, check=check)

        except asyncio.TimeoutError:
            await ctx.author.send("You timed out. Aborting.")
            raise commands.BadArgument("Poll creation cancelled.")

        return message.content

    @commands.command(
        description="Create a poll through DMs and send it to the current channel"
    )
    async def poll(self, ctx):
        try:
            await ctx.author.send("Welcome to the interactive poll maker")

        except discord.Forbidden:
            raise commands.BadArgument(
                "You must allow me to send you DMs. Poll creation cancelled."
            )

        title = await self.prompt(ctx, "What is the title of the poll?")

        emojis = [
            "\N{REGIONAL INDICATOR SYMBOL LETTER A}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER B}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER C}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER D}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER E}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER G}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER H}:",
            "\N{REGIONAL INDICATOR SYMBOL LETTER I}",
            "\N{REGIONAL INDICATOR SYMBOL LETTER J}",
        ]

        options = []

        await ctx.author.send(
            "Type options for your poll in separate messages.\n"
            f"When you are done, type `{ctx.prefix}done` to create the poll."
        )

        def check(ms):
            return ms.author == ctx.author and not ms.guild

        while len(options) <= 10:
            try:
                message = await self.bot.wait_for("message", timeout=180.0, check=check)

            except asyncio.TimeoutError:
                return await ctx.send(f"{ctx.tick(False)} You timed out. Aborting.")

            if message.content.lower() == f"{ctx.prefix}done":
                break

            options.append(message.content)

            await message.add_reaction(ctx.tick(True))

        await ctx.author.send("Sending your poll...")

        description = []

        for i, option in enumerate(options):
            description.append(f"{emojis[i]} | {option}")

        human_friendly = "\n".join(description)

        em = discord.Embed(
            title=title,
            description="Vote for an option by clicking the associated reaction."
            f"\n\n{human_friendly}",
            color=colors.PRIMARY,
        )

        if ctx.author.nick:
            name = f"{ctx.author.nick} ({str(ctx.author)})"
        else:
            name = str(ctx.author)

        em.set_author(name=name, icon_url=ctx.author.avatar_url)

        poll_message = await ctx.send("New Poll", embed=em)
        await ctx.author.send(ctx.tick(True, "Poll sent!"))

        for i in range(len(options)):
            await poll_message.add_reaction(emojis[i])

    async def send_sniped_message(self, ctx, message):
        em = discord.Embed(
            description=message.content,
            color=colors.PRIMARY,
            timestamp=message.created_at,
        )

        em.set_author(name=str(message.author), icon_url=message.author.avatar_url)
        em.set_footer(text=f"ID: {message.id} | Message sent")

        await ctx.send(embed=em)

    @commands.command(
        description="Get the previous or a specific deleted message in this channel",
    )
    async def snipe(self, ctx, message_id: int = None):
        sniped = [m for m in self.sniped_messages if m.channel == ctx.channel]

        if not sniped:
            return await ctx.send("I haven't sniped any messages in this channel.")

        if message_id:
            message = discord.utils.get(sniped, id=message_id)

            if not message:
                raise commands.BadArgument(
                    "I don't have a sniped message with that ID."
                )

        else:
            message = sniped[0]

        await self.send_sniped_message(ctx, message)

    @commands.command(description="Get all sniped messages in this channel",)
    async def sniped(self, ctx):
        sniped = [m for m in self.sniped_messages if m.channel == ctx.channel]

        if not sniped:
            return await ctx.send("I haven't sniped any messages in this channel.")

        entries = [f"{m.author} `(ID: {m.id})`" for m in sniped]

        em = discord.Embed(title="Sniped Messages", color=colors.PRIMARY)

        pages = ctx.embed_pages(entries, em)
        await pages.start(ctx)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        self.sniped_messages.insert(0, message)

        if len(self.sniped_messages) > 1000:
            self.sniped_messages.pop(len(self.sniped_messages) - 1)

    async def get_average_color(self, icon):
        bytes = io.BytesIO(await icon.read())
        partial = functools.partial(Image.open, bytes)
        image = await self.bot.loop.run_in_executor(None, partial)
        partial = functools.partial(image.resize, (1, 1))
        resized = await self.bot.loop.run_in_executor(None, partial)
        partial = functools.partial(resized.getpixel, (0, 0))
        color = await self.bot.loop.run_in_executor(None, partial)
        try:
            hex_string = "0x{:02x}{:02x}{:02x}".format(*color)
            return discord.Color(int(hex_string, 16))
        except TypeError:
            return None

    @commands.command(
        description="Get the avatar of a member.", aliases=["profilepic"],
    )
    async def avatar(self, ctx, *, member: discord.Member = None):
        if not member:
            member = ctx.author

        icon = member.avatar_url
        color = await self.get_average_color(icon) if icon else None
        color = color or member.color or colors.PRIMARY

        em = discord.Embed(color=color)

        if member.nick:
            name = f"{member.nick} ({str(member)})"
        else:
            name = str(member)

        em.set_author(name=name, icon_url=member.avatar_url)
        em.set_image(url=member.avatar_url)

        await ctx.send(embed=em)

    @commands.command(
        description="Get information about a user",
        aliases=["memberinfo", "ui", "whois"],
    )
    async def userinfo(self, ctx, *, user: GlobalUser = None):
        await ctx.trigger_typing()

        user = user or ctx.author

        is_member = isinstance(user, discord.Member)

        badge_mapping = {
            discord.UserFlags.staff: emojis.DISCORD_DEVELOPER,
            discord.UserFlags.partner: emojis.PARTNER,
            discord.UserFlags.hypesquad: emojis.HYPESQUAD_EVENTS,
            discord.UserFlags.bug_hunter: emojis.BUG_HUNTER,
            discord.UserFlags.bug_hunter_level_2: emojis.BUG_HUNTER_2,
            discord.UserFlags.hypesquad_bravery: emojis.HYPESQUAD_BRAVERY,
            discord.UserFlags.hypesquad_brilliance: emojis.HYPESQUAD_BRILLIANCE,
            discord.UserFlags.hypesquad_balance: emojis.HYPESQUAD_BALANCE,
            discord.UserFlags.early_supporter: emojis.EARLY_SUPPORTER,
            discord.UserFlags.verified_bot_developer: emojis.EARLY_VERIFIED_DEVELOPER,
        }

        badges = []
        for f in user.public_flags.all():
            badge = badge_mapping.get(f)

            if badge:
                badges.append(badge)

        desc = " ".join(badges)
        if user.id == self.bot.owner_id:
            created_or_owns = "created" if user.id == 224513210471022592 else "owns"
            desc += f"\n:gear: This user {created_or_owns} this bot."
        if user == self.bot.user:
            desc += "\n:wave:Hey, that's me!"
        if user.bot is True:
            verified = "verified " if user.public_flags.verified_bot else ""
            desc += f"\n:robot: This user is a {verified}bot."
        if is_member and user.id == ctx.guild.owner_id:
            desc += "\n<:owner:649355683598303260> This user owns this server."
        if is_member and user.premium_since:
            formatted = user.premium_since.strftime("%b %d, %Y at %#I:%M %p")
            desc += (
                "\n<:boost:649644112034922516> "
                "This user has been boosting this server since "
                f"{formatted}."
            )

        author = str(user)
        if is_member and user.nick:
            author += f" ({user.nick})"
        author += f" - {str(user.id)}"

        icon = user.avatar_url
        try:
            color = await self.get_average_color(icon) if icon else None
        except discord.HTTPException:
            color = None
        color = color or (user.color if is_member and user.color else colors.PRIMARY)

        em = discord.Embed(description=desc, color=color)

        em.set_thumbnail(url=user.avatar_url)
        em.set_author(name=author, icon_url=user.avatar_url)
        humanized = humanize.naturaltime(user.created_at)
        em.add_field(
            name=":clock1: Account Created",
            value=f"{humanize.naturaldate(user.created_at).capitalize()} ({humanized})",
            inline=True,
        )

        if is_member:
            humanized = humanize.naturaltime(user.joined_at)
            em.add_field(
                name="<:join:649722959958638643> Joined Server",
                value=f"{humanize.naturaldate(user.joined_at).capitalize()} ({humanized})",
                inline=True,
            )

            members = ctx.guild.members
            members.sort(key=lambda x: x.joined_at)
            position = members.index(user)
            em.add_field(name=":family: Join Position", value=position + 1)

            if user.roles[1:]:
                roles = ""
                for role in user.roles[1:]:
                    if len(roles + f"{role.mention} ") > 1012:
                        roles += "...and more"
                        break
                    roles += f"{role.mention} "
                em.add_field(name="Roles", value=roles, inline=False)

        shared = [
            g for g in self.bot.guilds if discord.utils.get(g.members, id=user.id)
        ]

        if not shared:
            em.set_footer(text="No servers shared")

        else:
            em.set_footer(text=f"{plural(len(shared)):server} shared")

        await ctx.send(embed=em)

    @commands.command(
        name="serverinfo",
        description="Get information about the current server",
        aliases=["guildinfo"],
    )
    async def serverinfo_command(self, ctx):
        await ctx.trigger_typing()
        guild = ctx.guild
        if guild.unavailable == True:
            return await ctx.send(
                "This guild is unavailable.\nWhat does this mean? I don't know either.\nMaybe Discord is having an outage..."
            )

        desc = ""
        if guild.description:
            desc += f"\n{guild.description}\n"
        if guild.large == True:
            desc += "\n:information_source: This guild is considered large (over 250 members)."

        icon = guild.icon_url
        color = await self.get_average_color(icon) if icon else None
        color = color or colors.PRIMARY

        em = discord.Embed(description=desc, color=color)

        em.set_thumbnail(url=guild.icon_url)
        if guild.banner_url:
            em.set_image(url=guild.banner_url)
        em.set_author(name=f"{guild.name} ({guild.id})", icon_url=guild.icon_url)
        em.add_field(
            name="<:owner:649355683598303260> Owner",
            value=guild.owner.mention,
            inline=True,
        )
        humanized = humanize.naturaltime(guild.created_at)
        em.add_field(
            name=":clock1: Server Created",
            value=f"{humanize.naturaldate(guild.created_at).capitalize()} ({humanized})",
            inline=True,
        )
        em.add_field(
            name="<:boost:649644112034922516> Nitro Boosts",
            value=f"Tier {guild.premium_tier} with {guild.premium_subscription_count} boosts",
            inline=True,
        )
        em.add_field(
            name=":earth_americas: Region",
            value=str(guild.region).replace("-", " ").upper(),
            inline=True,
        )
        em.add_field(name=":family: Members", value=len(guild.members), inline=True)
        em.add_field(
            name=":speech_balloon: Channels",
            value=f"<:text_channel:661798072384225307> {len(guild.text_channels)} • <:voice_channel:665577300552843294> {len(guild.voice_channels)}",
            inline=True,
        )

        # roles = ""
        # for role in member.roles[1:]:
        #     roles += f"{role.mention} "
        # em.add_field(
        #     name = "Roles",
        #     value = roles,
        #     inline = False
        # )
        await ctx.send(embed=em)

    @commands.command(
        name="snowstamp",
        description="Get timestamp from a Discord snowflake",
        hidden=True,
    )
    async def snowstamp_command(self, ctx, snowflake=None):
        if snowflake == None:
            return await ctx.send("Please specify a snowflake to convert.")
        await ctx.send(snowstamp(snowflake))

    def time_in_range(self, start, end, x):
        """Return true if x is in the range [start, end]"""
        if start <= end:
            return start <= x <= end
        else:
            return start <= x or x <= end

    @commands.command(description="Parse a Discord token", hidden=True)
    async def parsetoken(self, ctx, token):
        parsed = token.split(".")
        if len(parsed) != 3:
            return await ctx.send("This is not a Discord token :/")

        try:
            user_id = base64.b64decode(parsed[0])
        except binascii.Error:
            return await ctx.send("Failed to decode user id.")

        user_id = int(user_id)
        try:
            decoded = base64.b64decode(parsed[1] + "==")
        except binascii.Error:
            return await ctx.send("Failed to decode timestamp.")

        epoch = int.from_bytes(decoded, "big")
        timestamp = epoch + 1293840000
        created = d.utcfromtimestamp(timestamp)
        if not self.time_in_range(2015, 2040, created.year):
            created = created - timedelta(days=14975)

        created = created.strftime("%b %d, %Y at %#I:%M %p")
        em = discord.Embed(color=0x36393F)
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            em.description = f"ID: `{user_id}`\nCreated: `{created}`\nUser not found."
            return await ctx.send(embed=em)

        em.description = f"ID: `{user_id}`\nUsername: `{user}`\nBot: `{user.bot}`\nCreated: `{created}`"
        em.set_thumbnail(url=user.avatar_url)
        await ctx.send(embed=em)

    @commands.command(
        name="embed",
        description="Create a custom embed and send it to a specified channel.",
        aliases=["em"],
        hidden=True,
    )
    @commands.guild_only()
    @commands.is_owner()
    async def embed_command(self, ctx):
        def check(ms):
            # Look for the message sent in the same channel where the command was used
            # As well as by the user who used the command.
            return ms.channel == ctx.author.dm_channel and ms.author == ctx.author

        if (ctx.channel).__class__.__name__ == "DMChannel":
            await ctx.send("Please use this command in a server.")
            return

        await ctx.send("Check your DMs!", delete_after=5)
        await ctx.author.send(
            "**Create an embed:**\nWhat server would you like to send the embed to? Type `here` to send the embed where you called the command."
        )

        msg = await self.bot.wait_for("message", check=check)

        if msg == "here":
            em_guild = ctx.guild
        else:
            await ctx.author.send(
                "Custom servers not supported yet :(\nServer set to where you called the command."
            )
            em_guild = ctx.guild

        # Check to see if bot has permission to view perms

        await ctx.author.send(
            f"Server set to `{em_guild.name}`.\nWhat channel would you like to send to?"
        )

        msg = await self.bot.wait_for("message", check=check)

        # Check for permission here

        # while hasPermissionToSend == False:

    @commands.group(
        description="Search for things in a server.",
        aliases=["find"],
        invoke_without_command=True,
    )
    async def search(self, ctx):
        await ctx.send_help(ctx.command)

    def compile_list(self, list):
        msg = (
            f"Found **{len(list)}** {'matches' if len(list) > 1 else 'match'}! ```ini\n"
        )
        for i, member in enumerate(list):
            if member.nick:
                nick = f"{member.nick} - "
            else:
                nick = ""
            msg += f"\n[{i+1}] {nick}{member.name}#{member.discriminator} ({member.id})"
        msg += "\n```"
        return msg

    @search.command(
        name="username",
        description="Search server for a specified username",
        aliases=["user", "name"],
    )
    async def search_username(self, ctx, *, username):
        matches = []
        for member in ctx.guild.members:
            if username.lower() in member.name.lower():
                matches.append(member)
        if matches:
            pages = menus.MenuPages(
                source=SearchPages(matches), clear_reactions_after=True
            )
            return await pages.start(ctx)
            # return await ctx.send(self.compile_list(matches))
        await ctx.send("No matches found.")

    @search.command(
        name="nickname",
        description="Search server for a specified nickname",
        aliases=["nick"],
    )
    async def search_nickname(self, ctx, *, nickname):
        matches = []
        for member in ctx.guild.members:
            if member.nick:
                if nickname.lower() in member.nick.lower():
                    matches.append(member)
        if matches:
            pages = menus.MenuPages(
                source=SearchPages(matches), clear_reactions_after=True
            )
            return await pages.start(ctx)
        await ctx.send("No matches found.")

    @search.command(
        name="discriminator",
        description="Search server for a specified descrininator",
        aliases=["number", "discrim", "dis", "num"],
    )
    async def search_discriminator(self, ctx, discriminator: int):
        matches = []
        for member in ctx.guild.members:
            if discriminator == int(member.discriminator):
                matches.append(member)
        if matches:
            pages = menus.MenuPages(
                source=SearchPages(matches), clear_reactions_after=True
            )
            return await pages.start(ctx)
        await ctx.send("No matches found.")


def setup(bot):
    bot.add_cog(Tools(bot))
