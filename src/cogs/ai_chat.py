from __future__ import annotations

import discord
from discord.ext import commands
import google.generativeai as genai

from core import Cog, Context
from models import Guild, User, Scrim, Tourney
import config


class AIChat(Cog, name="AIChat(On Working:)"):
    def __init__(self, bot):
        self.bot = bot
        self.ai_available = False
        self.model = None
        self.model_name = None

        try:
            genai.configure(api_key=config.GEMINI_API_KEY)
            
            model_names = [
                "gemini-2.0-flash-001",  
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-2.5-flash",
                "gemini-2.5-flash-preview-05-20",
                "gemini-2.5-pro-preview-06-05"
            ]
           
            for model_name in model_names:
                try:
                    print(f"🔄 Trying model: {model_name}")
                    self.model = genai.GenerativeModel(model_name)
                    # Test the model with a simple prompt
                    test_response = self.model.generate_content("Hello, respond with just 'OK'")
                    if test_response.text:
                        self.ai_available = True
                        self.model_name = model_name
                        print(f"✅ AI Model loaded successfully: {model_name}")
                        break
                except Exception as e:
                    print(f"❌ Model {model_name} failed: {e}")
                    continue
                    
            if not self.ai_available:
                print("❌ No AI models available. AI features disabled.")
                
        except Exception as e:
            print(f"❌ Gemini AI initialization failed: {e}")
            self.ai_available = False

        # Your Discord server link for premium info
        self.premium_server_link = "https://discord.gg/rS58vTYeHc"

    async def get_bot_context(self, ctx: Context):
        """Fetch data from DB related to current guild and user"""
        guild_data = await Guild.get_or_none(guild_id=ctx.guild.id)
        user_data = await User.get_or_none(user_id=ctx.author.id)

        # Fetch active scrims in this server - FIXED: Use closed_at__isnull instead of closed
        active_scrims = await Scrim.filter(guild_id=ctx.guild.id, closed_at__isnull=True).all()
        scrims_info = []
        for scrim in active_scrims:
            channel = ctx.guild.get_channel(scrim.registration_channel_id)
            channel_name = channel.name if channel else "Deleted Channel"
            scrims_info.append(f"- {scrim.name} (Channel: #{channel_name})")

        # Fetch active tournaments in this server
        active_tourneys = await Tourney.filter(guild_id=ctx.guild.id).all()
        tourneys_info = []
        for tourney in active_tourneys:
            channel = ctx.guild.get_channel(tourney.registration_channel_id)
            channel_name = channel.name if channel else "Deleted Channel"
            prize_info = f" - Prize: {tourney.total_prize}" if tourney.total_prize else ""
            tourneys_info.append(f"- {tourney.name} (Channel: #{channel_name}{prize_info})")

        context_info = {
            "guild_name": ctx.guild.name,
            "user_name": ctx.author.display_name,
            "is_premium": getattr(guild_data, "is_premium", False),
            "user_xp": getattr(user_data, "xp", 0),
            "active_scrims": scrims_info,
            "active_tournaments": tourneys_info,
            "scrims_count": len(active_scrims),
            "tournaments_count": len(active_tourneys),
            "bot_name": self.bot.user.name,
            "bot_mention": self.bot.user.mention,
        }
        return context_info

    @commands.command(name="ai", help="Chat with AI — understands your ScrimX data.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def chat_with_ai(self, ctx: Context, *, message: str):
        """Main AI Chat command"""
        
        # Check if AI is available
        if not self.ai_available or not self.model:
            embed = discord.Embed(
                title="🤖 AI Service Unavailable",
                description=(
                    "The AI chat feature is currently disabled.\n\n"
                    "**Possible reasons:**\n"
                    "• AI service is under maintenance\n"
                    "• API limits reached\n"
                    "• Technical issues\n\n"
                    "Please try again later or contact support."
                ),
                color=0xff0000
            )
            return await ctx.send(embed=embed)

        await ctx.typing()

        # Check if user is asking about premium or upgrade
        premium_keywords = ["premium", "upgrade", "buy", "purchase", "subscribe", "pro", "donate", "payment"]
        if any(word in message.lower() for word in premium_keywords):
            embed = discord.Embed(
                title="💎 Upgrade to Premium",
                description=f"Join our official Discord server to get ScrimX Premium!\n\n👉 [Join Now]({self.premium_server_link})",
                color=0x00ff00,
            )
            embed.set_footer(text="ScrimX AI • Premium Info")
            return await ctx.send(embed=embed)

        # Check if user is mentioning the bot
        bot_mention_keywords = [f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>", self.bot.user.name.lower()]
        is_bot_mentioned = any(keyword in message.lower() for keyword in bot_mention_keywords)

        # Get context and generate response
        context_data = await self.get_bot_context(ctx)

        system_prompt = f"""
        You are ScrimX AI — a friendly assistant for a Discord bot that manages scrims, tournaments, and gaming events.
        
        Current Server Context:
        - Server Name: {context_data['guild_name']}
        - User: {context_data['user_name']}
        - User XP: {context_data['user_xp']}
        - Premium Status: {context_data['is_premium']}
        - Bot Name: {context_data['bot_name']}
        
        Active Scrims ({context_data['scrims_count']}):
        {chr(10).join(context_data['active_scrims']) if context_data['active_scrims'] else "No active scrims"}
        
        Active Tournaments ({context_data['tournaments_count']}):
        {chr(10).join(context_data['active_tournaments']) if context_data['active_tournaments'] else "No active tournaments"}
        
        Your personality:
        - Be helpful, concise, and engaging
        - Keep responses under 1500 characters
        - Use emojis occasionally to make it friendly
        - Focus on gaming, scrims, tournaments, and Discord bot functionality
        - If you don't know something, be honest about it
        
        Special Instructions:
        - If user asks about scrims/tournaments, use the active lists above
        - If user mentions the bot ({context_data['bot_mention']}), respond helpfully
        - Guide users to appropriate channels for scrims/tournaments
        - Be proactive in helping with gaming events
        
        User's message: {message}
        Bot mentioned: {is_bot_mentioned}
        """

        try:
            response = self.model.generate_content(system_prompt)
            
            if not response or not response.text:
                raise Exception("Empty response from AI")
                
            text = response.text

            # Ensure response isn't too long for Discord
            if len(text) > 2000:
                text = text[:1997] + "..."

            embed = discord.Embed(
                description=text,
                color=self.bot.color,
            )
            
            # Add server stats to embed if relevant
            if any(keyword in message.lower() for keyword in ['scrim', 'tournament', 'event', 'match']):
                stats_note = f"📊 This server has {context_data['scrims_count']} active scrims and {context_data['tournaments_count']} tournaments"
                if len(embed.description) + len(stats_note) < 2000:
                    embed.description += f"\n\n{stats_note}"

            embed.set_author(
                name=f"ScrimX AI Assistant • {self.model_name}", 
                icon_url=self.bot.user.display_avatar.url
            )
            await ctx.send(embed=embed)

        except Exception as e:
            error_msg = str(e)
            print(f"AI Generation Error: {error_msg}")
            
            # Specific error handling
            if "429" in error_msg:
                error_description = "API rate limit exceeded. Please try again in a minute."
            elif "500" in error_msg:
                error_description = "AI service is temporarily unavailable. Please try again later."
            elif "400" in error_msg:
                error_description = "Invalid request. Please rephrase your message."
            else:
                error_description = "An unexpected error occurred. Please try again."
            
            embed = discord.Embed(
                title="❌ AI Service Error",
                description=(
                    f"{error_description}\n\n"
                    f"**Model:** {self.model_name}\n"
                    f"**Error:** `{error_msg[:100]}`"
                ),
                color=0xff0000
            )
            await ctx.send(embed=embed)

    @commands.command(name="server_events")
    async def server_events(self, ctx: Context):
        """Show active scrims and tournaments in this server"""
        context_data = await self.get_bot_context(ctx)
        
        embed = discord.Embed(
            title=f"🎯 Active Events in {ctx.guild.name}",
            color=self.bot.color,
            timestamp=ctx.message.created_at
        )
        
        # Scrims section
        if context_data['active_scrims']:
            scrims_text = "\n".join(context_data['active_scrims'])
            embed.add_field(
                name=f"🏆 Active Scrims ({context_data['scrims_count']})",
                value=scrims_text,
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 Active Scrims",
                value="No active scrims in this server",
                inline=False
            )
        
        # Tournaments section
        if context_data['active_tournaments']:
            tourneys_text = "\n".join(context_data['active_tournaments'])
            embed.add_field(
                name=f"🎮 Active Tournaments ({context_data['tournaments_count']})",
                value=tourneys_text,
                inline=False
            )
        else:
            embed.add_field(
                name="🎮 Active Tournaments",
                value="No active tournaments in this server",
                inline=False
            )
        
        embed.set_footer(text="Use 'xai' command to ask me about these events!")
        await ctx.send(embed=embed)

    @commands.command(name="ai_status")
    async def ai_status(self, ctx: Context):
        """Check AI service status"""
        status = "🟢 **Online**" if self.ai_available else "🔴 **Offline**"
        model_name = self.model_name if self.model_name else "None"
        
        # Get server stats for status
        context_data = await self.get_bot_context(ctx)
        
        embed = discord.Embed(
            title="🤖 AI Service Status",
            color=0x00ff00 if self.ai_available else 0xff0000,
            timestamp=ctx.message.created_at
        )
        
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Model", value=model_name, inline=True)
        embed.add_field(name="Response Time", value="~2-5 seconds", inline=True)
        
        # Add server events info
        embed.add_field(
            name="📊 Server Events", 
            value=f"Scrims: {context_data['scrims_count']} | Tournaments: {context_data['tournaments_count']}",
            inline=False
        )
        
        if self.ai_available:
            embed.add_field(
                name="💡 Available Models", 
                value="• gemini-2.0-flash-001\n• gemini-2.5-flash\n• gemini-2.5-pro",
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ Notice", 
                value="AI features are currently disabled. Some commands may not work.",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="ai_switch")
    @commands.is_owner()
    async def switch_ai_model(self, ctx: Context, model_name: str):
        """Switch to a different AI model (Owner only)"""
        try:
            self.model = genai.GenerativeModel(model_name)
            # Test the model
            test_response = self.model.generate_content("Test")
            if test_response.text:
                self.ai_available = True
                self.model_name = model_name
                await ctx.success(f"✅ Switched to model: `{model_name}`")
            else:
                await ctx.error("❌ Model test failed")
        except Exception as e:
            await ctx.error(f"❌ Failed to switch model: `{e}`")
async def setup(bot):
    await bot.add_cog(AIChat(bot))