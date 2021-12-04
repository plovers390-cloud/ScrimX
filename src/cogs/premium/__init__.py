from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from core import Quotient

from core import Cog, Context
from discord.ext import commands, tasks
from models import User, Redeem, Guild, ArrayAppend, Timer
from utils import checks, strtime, IST
from datetime import datetime, timedelta
from tortoise.query_utils import Q

from contextlib import suppress

from .views import InvitePrime, PremiumView
import discord
import config

from .expire import activate_premium, remind_guild_to_pay, remind_user_to_pay, deactivate_premium, extra_guild_perks


class Premium(Cog):
    def __init__(self, bot: Quotient):
        self.bot = bot
        self.reminder_task = self.remind_peeps_to_pay.start()

    @commands.command()
    @checks.is_premium_user()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def boost(self, ctx: Context):
        """Upgrade your server with Quotient Premium."""

        def __use_prime_bot(g: discord.Guild) -> bool:
            return bool(g.get_member(config.PREMIUM_BOT))

        user = await User.get(user_id=ctx.author.id)
        if not user.premiums:
            return await ctx.error(
                "You have no Quotient Prime Boosts left.\n\nKindly purchase premium again to get 1 boost.\n"
            )

        guild = await Guild.get(guild_id=ctx.guild.id)

        if guild.premium_end_time and guild.premium_end_time > datetime.now(tz=IST):
            end_time = guild.premium_end_time + timedelta(days=30)

        else:
            end_time = datetime.now(tz=IST) + timedelta(days=30)

        prompt = await ctx.prompt(
            f"This server will be upgraded with Quotient Premium till {strtime(end_time)}."
            "\n\n*This action is irreversible.*",
            title="Are you sure you want to continue?",
        )
        if not prompt:
            return await ctx.simple(f"Alright, Aborting.")

        await user.refresh_from_db(("premiums",))
        if not user.premiums:
            return await ctx.send("don't be a dedh shana bruh")

        await Guild.get(pk=guild.pk).update(
            is_premium=True,
            made_premium_by=ctx.author.id,
            premium_end_time=end_time,
            embed_color=self.bot.config.PREMIUM_COLOR,
            bot_id=config.PREMIUM_BOT if __use_prime_bot(ctx.guild) else self.bot.user.id,
        )
        await User.get(pk=user.pk).update(
            premiums=user.premiums - 1, made_premium=ArrayAppend("made_premium", ctx.guild.id)
        )
        await self.bot.reminders.create_timer(end_time - timedelta(days=4), "guild_premium_reminder", guild=ctx.guild.id)
        await self.bot.reminders.create_timer(end_time, "guild_premium", guild_id=ctx.guild.id)

        await ctx.success(f"Congratulations, this server has been upgraded to Quotient Premium till {strtime(end_time)}.")

        if not __use_prime_bot(ctx.guild):
            _view = InvitePrime(ctx.guild.id)
            await ctx.send(embed=_view.embed_msg, view=_view)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def pstatus(self, ctx: Context):
        """Get your Quotient Premium status and the current server's."""
        user = await User.get_or_none(user_id=ctx.author.id)
        redeems = await Redeem.filter(user_id=ctx.author.id)  # manytomany soon :c
        guild = await Guild.filter(guild_id=ctx.guild.id).first()

        if not user.is_premium:
            atext = "\n> Activated: No!"

        else:
            atext = f"\n> Activated: Yes!\n> Expiry: `{strtime(user.premium_expire_time)}`\n> Boosts Left: {user.premiums}\n> Boosted Servers: {len(set(user.made_premium))}\n> Redeem Codes: {len(redeems)}"

        if not guild.is_premium:
            btext = "\n> Activated: No!"

        else:
            booster = ctx.guild.get_member(guild.made_premium_by) or await self.bot.fetch_user(guild.made_premium_by)
            btext = (
                f"\n> Activated: Yes!\n> Expiry Time: `{strtime(guild.premium_end_time)}`\n> Boosted by: **{booster}**"
            )

        embed = self.bot.embed(ctx, title="Quotient Premium", url=f"{self.bot.config.WEBSITE}")
        embed.add_field(name="User", value=atext, inline=False)
        embed.add_field(name="Server", value=btext, inline=False)
        return await ctx.send(embed=embed)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def perks(self, ctx: Context):
        """Get a list of all available perks you get when You purchase quotient premium."""
        return await ctx.premium_mango("*I love you, Buy Premium and I'll love you even more*\n*~ deadshot#7999*")

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if not self.bot.user.id == config.PREMIUM_BOT:
            return

        _g = await Guild.get_or_none(pk=guild.id)
        if not _g:
            return

        if not _g.is_premium:
            return await guild.leave()

        await Guild.get(pk=_g.pk).update(bot_id=self.bot.user.id, embed_color=config.PREMIUM_COLOR)
        await self.bot.cache.update_guild_cache(guild.id)
        await activate_premium(self.bot, guild)

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        _g = await Guild.get_or_none(pk=guild.id, bot_id=config.PREMIUM_BOT)
        if not _g:
            return

        if self.bot.user.id == config.PREMIUM_BOT:
            await Guild.get(pk=_g.pk).update(bot_id=config.MAIN_BOT)

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.id == config.MAIN_BOT:
            _g = await Guild.get_or_none(pk=member.guild.id, bot_id=config.PREMIUM_BOT)
            if _g:
                await self.bot.convey_important_message(member.guild, ("invite krlo vapis"))

    @tasks.loop(hours=48)
    async def remind_peeps_to_pay(self):
        async for user in User.filter(
            is_premium=True, premium_expire_time__lte=datetime.now(tz=IST) + timedelta(days=10)
        ):
            _u = await self.bot.getch(self.bot.get_user, self.bot.fetch_user, user.pk)
            if _u:
                if not await self.ensure_reminders(user.pk, user.premium_expire_time):
                    await self.bot.reminders.create_timer(user.premium_expire_time, "user_premium", user_id=user.pk)

                await remind_user_to_pay(_u, user)

        async for guild in Guild.filter(is_premium=True, premium_end_time__lte=datetime.now(IST) + timedelta(days=10)):
            _g = self.bot.get_guild(guild.pk)

            if not await self.ensure_reminders(guild.pk, guild.premium_end_time):
                await self.bot.reminders.create_timer(guild.premium_end_time, "guild_premium", guild_id=guild.pk)

            if _g:
                await remind_guild_to_pay(_g, guild)

    async def ensure_reminders(self, _id: int, _time: datetime) -> bool:
        return await Timer.filter(
            Q(event="guild_premium", extra={"args": [], "kwargs": {"guild_id": _id}})
            | Q(event="user_premium", extra={"args": [], "kwargs": {"user_id": _id}}),
            expires=_time,
        ).exists()

    def cog_unload(self):
        self.remind_peeps_to_pay.stop()

    @remind_peeps_to_pay
    async def before_loops(self):
        await self.bot.wait_until_ready()

    @Cog.listener()
    async def on_guild_premium_timer_complete(self, timer: Timer):
        guild_id = timer.kwargs["guild_id"]

        _g = await Guild.get_or_none(pk=guild_id)
        if not _g:
            return

        if not _g.premium_end_time == timer.expires:
            return

        _perks = "\n".join(await extra_guild_perks(guild_id))

        await deactivate_premium(guild_id)

        if (_ch := _g.private_ch) and _ch.permissions_for(_ch.guild.me).embed_links:

            _e = discord.Embed(
                color=discord.Color.red(), title="⚠️__**Quotient Prime Subscription Ended**__⚠️", url=config.SERVER_LINK
            )
            _e.description = (
                "This is to inform you that your subscription of Quotient Prime has been ended.\n\n"
                "*Following is a list of perks or data you lost:*"
            )

            _e.description += f"```diff\n{_perks}```"

            _roles = [
                role.mention
                for role in _ch.guild.roles
                if all((role.permissions.administrator, not role.managed, role.members))
            ]

            _view = PremiumView(label="Buy Quotient Prime")
            await _ch.send(
                embed=_e,
                view=_view,
                content=", ".join(_roles[:2]) if _roles else _ch.guild.owner.mention,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )

    @Cog.listener()
    async def on_user_premium_timer_complete(self, timer: Timer):
        user_id = timer.kwargs["user_id"]
        _user = await User.get_or_none(pk=user_id)
        if not _user:
            return

        if not _user.premium_expire_time == timer.expires:
            return

        _q = "UPDATE user_data SET is_premium = FALSE , made_premium = '{}' WHERE user_id = $1"
        await self.bot.db.execute(_q, user_id)

        member = await self.bot.get_or_fetch_member(self.bot.server, _user.pk)
        if member:
            await member.remove_roles(discord.Object(id=config.PREMIUM_ROLE))

    # @commands.command()
    # @commands.bot_has_permissions(embed_links=True)
    # async def changequo(self, ctx: Context):
    #     """Switch to another Quotient Premium bot."""

    #     if not await ctx.is_premium_guild():
    #         return await ctx.error("This server is not boosted. Please use `qboost`.")

    #     await self.bot.reminders.create_timer(
    #         datetime.now(tz=IST) + timedelta(minutes=1),
    #         "premium_activation",
    #         channel_id=ctx.channel.id,
    #         guild_id=ctx.guild.id,
    #     )

    #     await Guild.get(pk=ctx.guild.id).update(waiting_activation=True)

    #     _view = PremiumActivate(ctx.guild.id)
    #     await ctx.send(_view.initial_message, view=_view, file=await _view.image)

    # @Cog.listener()
    # async def on_premium_activation_timer_complete(self, timer: Timer):
    #     channel_id, guild_id = timer.kwargs["channel_id"], timer.kwargs["guild_id"]

    #     guild = await Guild.get(pk=guild_id)
    #     if not guild.is_premium or not guild.waiting_activation:
    #         return

    #     await guild.select_for_update().update(waiting_activation=False)

    #     channel = self.bot.get_channel(channel_id)
    #     await channel.send("Quotient Change request timed out. Kindly use `qchangequo` command again.")


def setup(bot) -> None:
    bot.add_cog(Premium(bot))
