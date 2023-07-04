import aiohttp
import discord
import os

from discord.ext import commands
from json import loads
from pathlib import Path

try:
    # Attempt to load the secrets from a file.
    secrets = loads(Path("secrets.json").read_text())
except FileNotFoundError:
    # This is used as a fallback when the secrets file doesn't exist.
    secrets = {"CHATGPT_API_KEY": os.environ["CHATGPT_API_KEY"]}

class Discuss(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations = {}
        
    # Thank you, vgmoose, for the following code snippet!
    # this function sends the text verabtim to the openai endpoint
    # it may need an initial prompt to get the conversation going
    async def send_to_gpt(self, conversation):
        # talk to the openai endpoint and make a request
        # https://beta.openai.com/docs/api-reference/completions/create
        headers = {
            "Authorization": f"Bearer {secrets['CHATGPT_API_KEY']}",
            "Content-Type": "application/json",
        }
        data = {
            "messages": conversation,
            "model": "gpt-3.5-turbo",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            ) as response:
                response.raise_for_status()
                response_data = await response.json()
                return response_data.get("choices", [{}])[0].get("message", {}).get("content", "")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.bot.user.mentioned_in(message) and message.author != self.bot.user:
            # Get the names of the bot, user, and server.
            bot_name = discord.utils.get(message.guild.members, id=self.bot.user.id).display_name
            user_name = message.author.display_name
            server_name = message.guild.name
            # Create the prompt using the above variables.
            prompt = (
                f"You are a friendly chat bot named {bot_name}. You are designed to assist users on a "
                f"Discord server called {server_name}. Currently, you are conversing with {user_name}. "
                f"Please provide helpful and concise responses, keeping in mind the 2000 character limit "
                f"for each message. Your goal is to provide valuable assistance and engage in meaningful "
                f"conversations with users. If possible, keep responses short and to the point, a few "
                f"sentences at most."
            )
            # If the channel isn't in the conversations dictionary, add it.
            if message.channel.id not in self.conversations:
                self.conversations[message.channel.id] = []
            conversation = self.conversations[message.channel.id]
            if len(conversation) > 100:
                while len(conversation) > 100:
                    conversation.pop(0)  # Remove the oldest messages.
            # Add the prompt to the conversation.
            conversation.append({
                "role": "system",
                "content": prompt
            })
            # If possible, change pings to be display names in the message.
            for mention in message.mentions:
                message.content = message.content.replace(mention.mention, mention.display_name)
            request = message.content
            # Add the request to the conversation.
            conversation.append({
                "role": "user",
                "content": request
            })
            # Make sure the request isn't empty.
            if request != "":
                async with message.channel.typing():
                    response = await self.send_to_gpt(conversation)
                    await message.reply(response, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Discuss(bot), guilds=[discord.Object(id=450846070025748480)])
