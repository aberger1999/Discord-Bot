import discord
from discord import app_commands
from discord.ext import commands
import random

'''def run_discord_bot():
    TOKEN = 'c7228bc178101df95490f43f463aaf6a81b85ee0dcd1140e6f0ccd0be959a412'
    client = discord.Client()

    @client.event
    async def on_ready():
        print(f'{client.user} is now running!')

    client.run(TOKEN)'''

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name = "hi", description = "If you're lonely", guild=discord.Object(id=806382276845633536)) #Add the guild ids in which the slash command will appear. If it should be in all, remove the argument, but note that it will take some time (up to an hour) to register the command if it's for all guilds.
async def first_command(interaction):
    await interaction.response.send_message("Hello!")

@tree.command(name = "ping", description = "ping-pong", guild=discord.Object(id=806382276845633536))
async def ping_command(interaction):
    await interaction.response.send_message("pong")

@tree.command(name = "eightball", description = "Magic eightball", guild=discord.Object(id=806382276845633536))
async def eightball_command(interaction, question: str):
    with open("discordbot/response.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response)
    await interaction.response.send_message(f"Question: {question}\nMagic 8-Ball says: {response}")

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=806382276845633536))
    print("Ready!")



##client = commands.Bot(command_prefix="=", intents=discord.Intents.all())

'''@client.event
async def on_ready():
    print("Success: Bot is connected to Discord")

@client.command()
async def ping(ctx):
    await ctx.send("Ping Pong Fucker!")

@client.command(aliases=["8ball", "eightball", "eight ball"])
async def magic_eightball(ctx, *, question):
    with open("discordbot/response.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response)

    await ctx.send(response)'''

client.run("MTEyOTk2NDQ4OTg5NTMxNzU2NQ.GkQVyx.5xYDvBWyQxMPcjfd6QVFFGyplwJRHdexwK_5OA")


