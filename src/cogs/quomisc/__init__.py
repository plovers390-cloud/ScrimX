from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from core import Quotient

import inspect
import itertools
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import discord
import pkg_resources
import psutil
import pygit2
from discord.ext import commands

from cogs.quomisc.helper import format_relative
from core import Cog, Context, QuotientView
from models import Commands, Guild, User, Votes
from utils import LinkButton, LinkType, QuoColor, checks, get_ipm, human_timedelta, truncate_string
from utils import emote

from .alerts import *
from .dev import *
from .views import MoneyButton, SetupButtonView, VoteButton


class Quomisc(Cog, name="quomisc"):
    def __init__(self, bot: Quotient):
        self.bot = bot
    @commands.command(aliases=("inv",))
    async def invite(self, ctx: Context):
        """ScrimX Invite Links."""
        v = discord.ui.View(timeout=None)
        v.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link, label="Invite ScrimX", url=self.bot.config.BOT_INVITE, row=1
            )
        )

        await ctx.reply(view=v)

    async def make_private_channel(self, ctx: Context) -> discord.TextChannel:
        support_link = f"[Support Server]({ctx.config.SERVER_LINK})"
        invite_link = f"[Invite Me]({ctx.config.BOT_INVITE})"

        guild = ctx.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True,
                manage_channels=True,
            ),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
        }
        channel = await guild.create_text_channel(
            "ScrimX-private", overwrites=overwrites, reason=f"Made by {str(ctx.author)}"
        )
        await Guild.filter(guild_id=ctx.guild.id).update(private_channel=channel.id)

        e = self.bot.embed(ctx)
        e.add_field(
            name="**What is this channel for?**",
            inline=False,
            value="This channel is made for ScrimX to send important announcements and activities that need your attention. If anything goes wrong with any of my functionality I will notify you here. Important announcements from the developer will be sent directly here too.\n\nYou can test my commands in this channel if you like. Kindly don't delete it , some of my commands won't work without this channel.",
        )
        e.add_field(
            name="**__Important Links__**", value=f"{support_link} | {invite_link}", inline=False
        )

        links = [LinkType("Support Server", ctx.config.SERVER_LINK)]
        view = LinkButton(links)
        m = await channel.send(embed=e, view=view)
        await m.pin()

        return channel

    @commands.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_channels=True, manage_webhooks=True)
    async def setup_cmd(self, ctx: Context):
        """
        Setup ScrimX in the current server.
        This creates a private channel in the server. You can rename that if you like.
        ScrimX requires manage channels and manage wehooks permissions for this to work.
        You must have manage server permission.
        """

        _view = SetupButtonView(ctx)
        _view.add_item(QuotientView.tricky_invite_button())
        record = await Guild.get(guild_id=ctx.guild.id)

        if record.private_ch is not None:
            return await ctx.error(f"You already have a private channel ({record.private_ch.mention})", view=_view)
        channel = await self.make_private_channel(ctx)
        await ctx.success(f"Created {channel.mention}", view=_view)

    def get_bot_uptime(self, *, brief=False):
        return human_timedelta(self.bot.start_time, accuracy=None, brief=brief, suffix=False)

    @staticmethod
    def format_commit(commit):  # source: R danny
        short, _, _ = commit.message.partition("\n")
        short_sha2 = commit.hex[0:6]
        commit_tz = timezone(timedelta(minutes=commit.commit_time_offset))
        commit_time = datetime.fromtimestamp(commit.commit_time).astimezone(commit_tz)

        # [`hash`](url) message (offset)
        offset = format_relative(commit_time.astimezone(timezone.utc))
        return f"[`{short_sha2}`](https://github.com/Spiiikkkeee?tab=repositories{commit.hex}) {truncate_string(short,40)} ({offset})"

    def get_last_commits(self, count=3):
        repo = pygit2.Repository(".git")
        commits = list(itertools.islice(repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL), count))
        return "\n".join(self.format_commit(c) for c in commits)

    @commands.command(aliases=("stats",))
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def about(self, ctx: Context):
        """Statistics of ScrimX."""
        db_latency = await self.bot.db_latency
# ✅ Safe version handling
        try:
            version = pkg_resources.get_distribution("discord.py").version
        except Exception:
            version = getattr(discord, "__version__", "unknown")

        # ✅ Safe commit retrieval (prevents pygit2 crash)
        try:
            revision = self.get_last_commits()
        except Exception:
            revision = "No recent commits found."

        total_memory = psutil.virtual_memory().total >> 20
        used_memory = psutil.virtual_memory().used >> 20
        cpu_used = str(psutil.cpu_percent())

        total_members = sum(g.member_count for g in self.bot.guilds)
        cached_members = len(self.bot.users)

        total_command_uses = await Commands.all().count()
        user_invokes = await Commands.filter(user_id=ctx.author.id, guild_id=ctx.guild.id).count() or 0
        server_invokes = await Commands.filter(guild_id=ctx.guild.id).count() or 0

        chnl_count = Counter(map(lambda ch: ch.type, self.bot.get_all_channels()))

        owner = await self.bot.getch(self.bot.get_user, self.bot.fetch_user, 584926650492387351)

        msges = self.bot.seen_messages

        embed = discord.Embed(description="Latest Changes:\n" + revision)
        embed.title = "ScrimX Official Support Server"
        embed.description =( "ScrimX is developed and maintained by the **ScrimX Team**.\n"
            "🖥️ **Language Used:** Python 🐍\n"
            "⚙️ **Library:** discord.py\n\n"
            "🚀 Built to simplify **scrim management**, **Tournamet setups**, and **server automation** "
            "for Discord communities.")
        embed.url = ctx.config.SERVER_LINK
        embed.colour = self.bot.color
        embed.set_author(name=str(owner), icon_url=owner.display_avatar.url)

        guild_value = len(self.bot.guilds)

        embed.add_field(name="Servers", value=f"{guild_value:,} total\n{len(self.bot.shards)} shards")
        embed.add_field(name="Uptime", value=f"{self.get_bot_uptime(brief=True)}\n{msges:,} messages seen")
        embed.add_field(name="Members", value=f"{total_members:,} Total\n{cached_members:,} cached")
        
        links = [LinkType("Support Server", ctx.config.SERVER_LINK), LinkType("Invite Me", ctx.config.BOT_INVITE)]
        await ctx.send(embed=embed, embed_perms=True, view=LinkButton(links))

    @commands.command()
    async def ping(self, ctx: Context):
        """Check how the bot is doing"""
        await ctx.send(f"Bot: `{round(self.bot.latency*1000, 2)} ms`, Database: `{await self.bot.db_latency}`")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx: Context, *, new_prefix: str = None):
        """Change your server's prefix"""

        if not new_prefix:
            prefix = self.bot.cache.guild_data[ctx.guild.id].get("prefix", "x")
            return await ctx.simple(f"Prefix for this server is `{prefix}`")

        if len(new_prefix) > 5:
            return await ctx.error(f"Prefix cannot contain more than 5 characters.")

        self.bot.cache.guild_data[ctx.guild.id]["prefix"] = new_prefix
        await Guild.filter(guild_id=ctx.guild.id).update(prefix=new_prefix)
        await ctx.success(f"Updated server prefix to: `{new_prefix}`")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    @checks.is_premium_guild()
    async def color(self, ctx: Context, *, new_color: QuoColor):
        """Change color of ScrimX's embeds"""
        color = int(str(new_color).replace("#", ""), 16)  # The hex value of a color.

        self.bot.cache.guild_data[ctx.guild.id]["color"] = color
        await Guild.filter(guild_id=ctx.guild.id).update(embed_color=color)
        await ctx.success(f"Updated server color.")
    @commands.command()
    async def credits(self, ctx: Context):
     """
     Detailed credits and acknowledgement
     """
     credit_text = f"""
     {emote.check} **Source Code Credits**

     {emote.crown} **Original Creator**
      **Rohit** - Discord ID: (<@548163406537162782>)
       Original Quotient Bot Developer
       Made the source code publicly available

     {emote.check} **My Contributions**
     {emote.check} **Bug Fixes** - Fixed bugs that were in the original code  
     {emote.check} **New Features** - Added new commands and functionality  
     {emote.check} **Code Improvement** - Improved performance and reliability  
     {emote.check} **Customization** - Modified according to my specific needs

     {emote.check} **Acknowledgement**
     I give full credit to Rohit for creating the original Quotient bot.  
     Because of his open source code, I was able to build my improved version.

     > **Note:** This is a modified version of the original Quotient bot
     > Original Developer: **Rohit** (<@548163406537162782>)
     """

     embed = discord.Embed(
        title=f"{emote.bot} Development Credits",
        description=credit_text,
        color=0x5865F2,
        timestamp=ctx.message.created_at
     )
    
     embed.add_field(
        name=f"{emote.bot_devloper} Original Project",
        value="Quotient Bot",
        inline=True
     )
    
     embed.add_field(
        name=f"{emote.verified_bot} Status",
        value="Enhanced Version",
        inline=True
     )
    
     embed.add_field(
        name=f"{emote.bot_devloper} Original Developer",
        value="Rohit\n(<@548163406537162782>)",
        inline=True
     )
    
     embed.set_thumbnail(url=self.bot.user.display_avatar.url)
     embed.set_footer(text=f"Building upon open-source innovation")
    
     await ctx.send(embed=embed)
    @commands.command()
    @checks.is_premium_guild()
    @commands.has_permissions(manage_guild=True)
    async def footer(self, ctx: Context, *, new_footer: str):
        """Change footer of embeds sent by ScrimX"""
        if len(new_footer) > 50:
            return await ctx.success(f"Footer cannot contain more than 50 characters.")

        self.bot.cache.guild_data[ctx.guild.id]["footer"] = new_footer
        await Guild.filter(guild_id=ctx.guild.id).update(embed_footer=new_footer)
        await ctx.send(f"Updated server footer.")

async def setup(bot: Quotient) -> None:
    await bot.add_cog(Quomisc(bot))
    await bot.add_cog(Dev(bot))
    await bot.add_cog(QuoAlerts(bot))
