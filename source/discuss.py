import aiohttp
import asyncio
import datetime
import discord
import json
import os
import pytz
import random

from discord.ext import commands
from json import loads
from logger import create_logger
from pathlib import Path


with open('config.json') as f:
    config = json.load(f)


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
        self.logger = create_logger(self.__class__.__name__)
        
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
            "model": "gpt-4o",
        }
        # Retry the request up to 3 times if it fails.
        retry_count = 0
        # Keep trying until the request succeeds or the retry limit is reached.
        while True:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        return response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    elif response.status == 400 and retry_count < 3:
                        # Wait for a certain period of time before retrying.
                        await asyncio.sleep(5)
                        retry_count += 1
                        # Clear the conversation on the final try.
                        if retry_count == 3:
                            conversation = conversation[-2:]
                        continue
                    else:
                        response.raise_for_status()


    # Every twelve hours, a prompt will be sent to the main discussion channel.
    # Currently, it is either a fact or a question about a conversation starter.
    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        discussion_starters = config['discussion_starters']
        channel = self.bot.get_channel(config["#chat-hangout"])
        # Keep the loop running until the bot is closed.
        while not self.bot.is_closed():
            now = datetime.datetime.now(pytz.timezone('UTC'))
            if now.hour < 12:
                next_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
            else:
                next_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
            seconds_until_next_time = (next_time - now).total_seconds()
            self.logger.info(f"The next discussion starter will be sent at {next_time}.")
            await asyncio.sleep(seconds_until_next_time)
            # The prompt for stating a fact about a discussion starter.
            fact_prompt = (
                f"Please state an interesting fact about {random.choice(discussion_starters)}. "
                f"If you state a fact, you can start with 'Did you know that...?' "
                f"Please make sure you give decent information. Two sentences is great."
                f"Just state the fact by itself, nothing such as 'Sure!'"
            )
            # The prompt for asking a question about a discussion starter.
            question_prompt = (
                f"Please ask a question about {random.choice(discussion_starters)}. "
                f"This question can be specific or general, but it should be engaging. "
                f"Some ideas include asking about favorites, or asking for recommendations. "
                f"Please refrain from asking yes or no questions, though. "
                f"Just state the question by itself, nothing such as 'Sure!'"
            )
            prompt = random.choice([fact_prompt, question_prompt])
            # If the channel isn't in the conversations dictionary, add it.
            if channel.id not in self.conversations:
                self.conversations[channel.id] = []
            conversation = self.conversations[channel.id]
            # Add the prompt to the conversation.
            conversation.append({
                "role": "system",
                "content": prompt
            })
            async with channel.typing():
                # Log the estimation of tokens that will be used.
                self.logger.info("Sending request to GPT-4 estimated to use "
                    f"{len(prompt)} tokens.")
                response = await self.send_to_gpt(conversation)
                await channel.send(response)
            await asyncio.sleep(60)


    # If the bot is mentioned, it will respond to the message with a GPT-4 response.
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.bot.user.mentioned_in(message) and message.author != self.bot.user and not message.mention_everyone \
            and message.channel == self.bot.get_channel(config["#bot-discussion"]):
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
            if len(conversation) > 30:
                while len(conversation) > 30:
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
                    # Log the estimation of tokens that will be used
                    self.logger.info("Sending request to GPT-4 estimated to use "
                        f"{len(request) + len(prompt)} tokens.")
                    response = await self.send_to_gpt(conversation)
                    await message.reply(response, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Discuss(bot), guilds=[discord.Object(id=450846070025748480)])
