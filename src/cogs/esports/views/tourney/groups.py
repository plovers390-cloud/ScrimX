from __future__ import annotations

from ...views.base import EsportsBaseView

from models import Tourney, TMSlot

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from core import Quotient

from utils import inputs, get_chunks, emote

from core import Context
import discord
import config


class TourneyGroupManager(EsportsBaseView):
    def __init__(self, ctx: Context, *, tourney: Tourney, size: int = 20):
        super().__init__(ctx, timeout=60, title="Tourney Group Manager")

        self.ctx = ctx
        self.tourney = tourney
        self.size = size
        self.bot: Quotient = ctx.bot

    @staticmethod
    def initial_embed(tourney: Tourney, size: int) -> discord.Embed:
        e = discord.Embed(color=0x00FFB3, title="Tourney Group Manager")
        e.description = (
            f"**[Tourney Slot Manager]({config.SERVER_LINK})** ─ {tourney}\n"
            f"**Group Size: `{size}`**\n\n"
            "• Click `Publish` to send group embeds in a channel.\n"
            "• Click `Give Roles` to provide group roles to team leaders.\n"
        )

        return e

    @discord.ui.button(custom_id="publish_groups", label="Publish Group List")
    async def publish_tourney_groups(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        m = await self.ask_embed(
            "Kindly mention the channel where you want me to send group list.\n\n"
            "`Make sure I have embed_links and manage_webhooks permission there.`"
        )

        _channel = await inputs.channel_input(self.ctx, self.check, delete_after=True)
        await self.ctx.maybe_delete(m)

        if not _channel.permissions_for(self.ctx.guild.me).manage_webhooks:
            return await self.error_embed(f"Make sure I have `manage_webhooks` permission in {_channel.mention}.")

        _list = []

        for idx, _chunk in enumerate(get_chunks(await self.tourney.assigned_slots.all(), self.size), start=1):
            e = discord.Embed(color=0x00FFB3, title=f"{self.tourney.name} Group {idx}")
            e.set_footer(text=self.ctx.guild.name, icon_url=getattr(self.ctx.guild.icon, "url", discord.Embed.Empty))
            e.description = ""
            for count, _slot in enumerate(_chunk, start=1):
                e.description += (
                    f"`{count:02}` • **[{_slot.team_name}]({_slot.confirm_jump_url})** (<@{_slot.leader_id}>)\n"
                )

            _list.append(e)

        _view = GroupListView(self.ctx, tourney=self.tourney, size=self.size, channel=_channel, embeds=_list)
        await interaction.followup.send(embed=GroupListView.initial_embed(self.tourney), view=_view)

    @discord.ui.button(custom_id="give_group_roles", label="Give Roles")
    async def give_group_roles(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        m = await self.ask_embed(
            f"Write the group number and the name of group role.\n"
            "**Format:** `Group Number, Name of Group Role`\n\n"
            "Note that you can also mention the role instead of name to give it to users, "
            "or just write its name, if there is no role of that name, Quotient"
            "will create the role and give it to group leaders.\n\n"
            "**Example:**```1, @group_role\n2, Group role\n3, @3rd_group```\n"
            "*Enter upto 5 roles at a time.*"
        )

        _roleinfo = await inputs.string_input(self.ctx, self.check, delete_after=True)
        await self.ctx.safe_delete(m)

        if (_roleinfo := _roleinfo.strip()) == "cancel":
            return

        _split = _roleinfo.split("\n")

        if len(_split) > 5:
            return await self.error_embed(f"Group Roles can be given to upto 5 groups at a time.")

        for _group in _split:
            try:
                group, role = _group.strip().split(",")
            except ValueError:
                return await self.error_embed(f"Invalid format given in `line {_split.index(_group) + 1}`.")

        await self.ctx.send(_split)


class GroupListView(EsportsBaseView):
    def __init__(
        self,
        ctx: Context,
        *,
        tourney: Tourney,
        size: int,
        channel: discord.TextChannel,
        embeds: List[discord.Embed],
    ):
        super().__init__(ctx, timeout=30, title="Group List Publisher")

        self.ctx = ctx
        self.bot: Quotient = ctx.bot
        self.tourney = tourney
        self.size = size
        self.channel = channel
        self.embeds = embeds

    @staticmethod
    def initial_embed(tourney: Tourney) -> discord.Embed:
        _e = discord.Embed(
            color=0x00FFB3,
            description=(
                f"**How would you like to publish the group list of {tourney}?**\n\n"
                "• `Webhook` will create a webhook in the channel and will send group embeds with your server's logo and name.\n"
                "• `Bot Option` will just make Quotient send the embeds.\n\n"
                "*Webhook Option is more cool.*"
            ),
        )

        return _e

    @discord.ui.button(custom_id="publish_g_hook", emoji="<a:diamond:899295009289949235>", label="Webhook (Recommended)")
    async def publish_groups_webhook(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            _webhook = await self.channel.create_webhook(
                name="Quotient Group List", reason=f"Created by {self.ctx.author} to send group list"
            )
        except Exception as e:
            return await self.error_embed(e)

        m = await self.ctx.simple(f"Publishing, please wait {emote.loading}")
        for _chunk in get_chunks(self.embeds, 10):
            await _webhook.send(
                embeds=_chunk,
                username=self.ctx.guild.name,
                avatar_url=getattr(self.ctx.guild.icon, "url", None),
            )

        await _webhook.delete()
        await self.ctx.safe_delete(m)
        m = await self.ctx.success("Group list published.")
        await self.ctx.safe_delete(m, 3)

    @discord.ui.button(custom_id="publish_g_bot", emoji="<:pain:837567768106238002>", label="With Bot")
    async def publish_groups_bot(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        m = await self.ctx.simple(f"Publishing, please wait {emote.loading}")
        for _chunk in get_chunks(self.embeds, 10):
            await self.channel.send(embeds=_chunk)

        await self.ctx.safe_delete(m)
        m = await self.ctx.success("Group list published.")
        await self.ctx.safe_delete(m, 3)

    @discord.ui.button(custom_id="publish_g_delete", emoji=emote.trash)
    async def publish_groups_delete(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.delete_original_message()
