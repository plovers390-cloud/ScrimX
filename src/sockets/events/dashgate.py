from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core import Quotient

from core import Cog
from models import Guild

__all__ = ("DashboardGate",)


class DashboardGate(Cog):
    def __init__(self, bot: Quotient):
        self.bot = bot

    @Cog.listener()
    async def on_request__guild_permissions(self, data):

        guild_ids = data["guild_ids"]
        user_id = data["user_id"]

        result = {}

        for guild_id in guild_ids:
            guild_id = int(guild_id)

            guild = self.bot.get_guild(guild_id)
            if not guild:
                result[guild_id] = -1
                continue

            member = await self.bot.get_or_fetch_member(guild, user_id)

            perms = 1

            further_checks = True
            if member.guild_permissions.manage_guild:
                further_checks = False
                perms = 2

            if further_checks:

                g_record = await Guild.get(pk=guild_id)
                _roles = [str(_.id) for _ in member.roles]

                if any(i in g_record.dashboard_access["embed"] for i in _roles):
                    perms *= 3

                if any(i in g_record.dashboard_access["scrims"] for i in _roles):
                    perms *= 5

                if any(i in g_record.dashboard_access["tourney"] for i in _roles):
                    perms *= 7

                if any(i in g_record.dashboard_access["slotm"] for i in _roles):
                    perms *= 11

            result[guild_id] = perms

        await self.bot.sio.emit("guild_permissions", result)
