from utils import emote
import discord


class PremiumView(discord.ui.View):
    def __init__(self, text="*This feature requires you to have Quotient Premium.*"):
        super().__init__(timeout=None)
        self.text = text
        self.add_item(
            discord.ui.Button(url="https://quotientbot.xyz/premium/buy", emoji=emote.diamond, label="Try Premium")
        )

    def premium_embed(self) -> discord.Embed:
        _e = discord.Embed(
            color=discord.Color.gold(), description=f"**You discovered a premium feature <a:premium:807911675981201459>**"
        )

        _e.description += (
            f"\n{self.text}\n\n**Quotient Premium includes:**\n"
            "- Host Unlimited Scrims and Tournaments.\n"
            "- Unlimited tagcheck and easytag channels.\n"
            "- Custom footer and color of all embeds bot sends.\n"
            "- Custom reactions for tourney and scrims.\n"
            "- Unlimited ssverification and media partner channels.\n"
            "- Premium role in our server and 10+ other benefits..."
        )
        _e.set_image(url="https://cdn.discordapp.com/attachments/851846932593770496/901494096579936318/premium.png")
        # _e.set_footer(text="Buy Premium and I'll love you even more - deadshot#7999")
        return _e
