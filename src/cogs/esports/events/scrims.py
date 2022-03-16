from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from core import Quotient

from core import Cog
from models import Scrim, AssignedSlot, ArrayRemove, Timer, BannedTeam, BanLog

from ..helpers import (
    add_role_and_reaction,
    scrim_end_process,
    before_registrations,
    cannot_take_registration,
    check_scrim_requirements,
    available_to_reserve,
    toggle_channel,
    scrim_work_role,
    registration_open_embed,
    should_open_scrim,
    purge_channel,
    purge_role,
)
from constants import EsportsLog, IST, Day, EsportsRole, AutocleanType
from contextlib import suppress
from datetime import datetime, timedelta
from unicodedata import normalize

import discord
import asyncio
import utils


class ScrimEvents(Cog):
    def __init__(self, bot: Quotient):
        self.bot = bot

        self.__scrim_lock = asyncio.Lock()

    @Cog.listener("on_message")
    async def on_scrim_registration(self, message: discord.Message):

        if not message.guild or message.author.bot:
            return

        channel_id = message.channel.id

        if channel_id not in self.bot.cache.scrim_channels:
            return

        scrim = await Scrim.get_or_none(
            registration_channel_id=channel_id,
        )

        if scrim is None:  # Scrim is possibly deleted
            return self.bot.cache.scrim_channels.discard(channel_id)

        scrim_role = scrim.role
        modrole = scrim.modrole

        if scrim.opened_at is None or scrim_role is None:
            return

        if modrole and modrole in message.author.roles:
            return

        if not before_registrations(message, scrim_role):
            return await cannot_take_registration(message, scrim)

        message.content = normalize("NFKC", message.content.lower())

        if not await check_scrim_requirements(self.bot, message, scrim):
            return

        async with self.__scrim_lock:
            ctx = await self.bot.get_context(message)

            teamname = utils.find_team(message)

            scrim = await Scrim.get_or_none(pk=scrim.id)

            if not scrim or scrim.closed:  # Scrim is deleted or closed.
                return

            try:
                slot_num = scrim.available_slots[0]
            except IndexError:
                return

            _team = {message.author.id}
            for _ in message.mentions:
                if not _.bot:
                    _team.add(_.id)

            slot = await AssignedSlot.create(
                user_id=ctx.author.id,
                team_name=utils.truncate_string(teamname, 30),
                num=slot_num,
                jump_url=message.jump_url,
                message_id=message.id,
                members=_team,
            )

            await scrim.assigned_slots.add(slot)

            await Scrim.filter(pk=scrim.id).update(available_slots=ArrayRemove("available_slots", slot_num))
            self.bot.loop.create_task(add_role_and_reaction(ctx, scrim.role))

            if len(scrim.available_slots) == 1:
                await scrim_end_process(ctx, scrim)

    # ==========================================================================================================
    # ==========================================================================================================

    @Cog.listener()
    async def on_scrim_open_timer_complete(self, timer: Timer):
        """This listener opens the scrim registration at time."""

        scrim_id = timer.kwargs["scrim_id"]
        scrim = await Scrim.get_or_none(pk=scrim_id)

        if not scrim:  # we don't want to do anything if the scrim is deleted
            return

        if scrim.open_time != timer.expires:  # If time is not same return :)
            return

        await Scrim.filter(pk=scrim.id).update(
            open_time=scrim.open_time + timedelta(hours=24),
        )

        await self.bot.reminders.create_timer(
            scrim.open_time + timedelta(hours=24),
            "scrim_open",
            scrim_id=scrim.id,
        )  # we don't want to risk this

        if scrim.toggle is not True or not Day(utils.day_today()) in scrim.open_days:
            return

        if scrim.opened_at and scrim.opened_at.strftime("%d-%b-%Y %I:%M %p") == datetime.now(tz=IST).strftime(
            "%d-%b-%Y %I:%M %p"
        ):
            return  # means we are having multiple timers for a single scrims :c shit

        guild = scrim.guild

        if not guild:
            return

        if not await should_open_scrim(scrim):
            return

        if not guild.chunked:
            self.bot.loop.create_task(guild.chunk())

        oldslots = await scrim.assigned_slots
        await AssignedSlot.filter(id__in=(slot.id for slot in oldslots)).delete()

        await scrim.assigned_slots.clear()

        # here we insert a list of slots we can give for the registration.
        # we insert only the empty slots not the reserved ones to avoid extra queries during creation of slots for reserved users.

        await self.bot.db.execute(
            """
            UPDATE public."sm.scrims" SET available_slots = $1 WHERE id = $2
            """,
            await available_to_reserve(scrim),
            scrim.id,
        )

        scrim_role = scrim.role
        async for slot in scrim.reserved_slots.all():
            assinged_slot = await AssignedSlot.create(
                num=slot.num,
                user_id=slot.user_id,
                team_name=slot.team_name,
                jump_url=None,
            )

            await scrim.assigned_slots.add(assinged_slot)

            if slot.user_id:
                with suppress(AttributeError):
                    self.bot.loop.create_task(guild.get_member(slot.user_id).add_roles(scrim_role))

        await Scrim.filter(pk=scrim.id).update(
            opened_at=datetime.now(tz=IST),
            closed_at=None,
            slotlist_message_id=None,
        )

        self.bot.loop.create_task(scrim.ensure_match_timer())

        await asyncio.sleep(0.2)

        # Opening Channel for Normal Janta
        registration_channel = scrim.registration_channel
        open_role = scrim.open_role

        _e = await registration_open_embed(scrim)

        await registration_channel.send(
            content=scrim_work_role(scrim, EsportsRole.ping),
            embed=_e,
            allowed_mentions=discord.AllowedMentions(roles=True, everyone=True),
        )

        self.bot.cache.scrim_channels.add(registration_channel.id)

        await toggle_channel(registration_channel, open_role, True)
        self.bot.dispatch("scrim_log", EsportsLog.open, scrim)

    @Cog.listener()
    async def on_autoclean_timer_complete(self, timer: Timer):
        scrim_id = timer.kwargs["scrim_id"]

        scrim = await Scrim.get_or_none(pk=scrim_id)

        if not scrim:
            return

        if timer.expires != scrim.autoclean_time:
            return

        await Scrim.filter(pk=scrim.id).update(autoclean_time=scrim.autoclean_time + timedelta(hours=24))
        await self.bot.reminders.create_timer(scrim.autoclean_time + timedelta(hours=24), "autoclean", scrim_id=scrim.id)

        if not scrim.toggle:
            return

        guild = scrim.guild

        async with self.__scrim_lock:
            if AutocleanType.channel in scrim.autoclean:
                self.bot.loop.create_task(self.__purge_channel(scrim.registration_channel))

            if AutocleanType.role in scrim.autoclean:
                async for slot in scrim.assigned_slots.all():
                    member = await self.bot.get_or_fetch_member(guild, slot.user_id)
                    if member:
                        with suppress(discord.HTTPException):
                            await member.remove_roles(discord.Object(id=scrim.role_id))

                if guild and not guild.chunked:
                    self.bot.loop.create_task(guild.chunk())

                role = scrim.role
                with suppress(AttributeError, discord.HTTPException):
                    for m in role.members:
                        await m.remove_roles(role)

    async def __purge_channel(self, channel=None):
        with suppress(discord.HTTPException, AttributeError):
            await channel.purge(limit=100, check=lambda x: not x.pinned)

    @Cog.listener()
    async def on_scrim_ban_timer_complete(self, timer: Timer):
        scrims = timer.kwargs["scrims"]
        user_id = timer.kwargs["user_id"]

        reason = timer.kwargs["reason"]

        new_reason = ("[Auto-Unban] because ban time's up.") + f"\nBanned for: {reason}" if reason else ""

        scrims = await Scrim.filter(pk__in=scrims)
        if not scrims:
            return

        guild = scrims[0].guild
        if not guild:
            return

        count = 0
        for scrim in scrims:
            bans = await scrim.banned_teams.filter(user_id=user_id)
            c = await BannedTeam.filter(pk__in=[_.pk for _ in bans]).delete()
            count += c

        if not count:
            return

        if banlog := await BanLog.get_or_none(guild_id=guild.id):
            await banlog.log_unban(user_id, guild.me, scrims, new_reason)
