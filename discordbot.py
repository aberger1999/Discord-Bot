import discord
from discord.ext import commands
import random

client = commands.Bot(command_prefix="=", intents=discord.Intents.all())

@client.event
async def on_ready():
    print("Success: Bot is connected to Discord")

@client.command()
async def ping(ctx):
    await ctx.author.send("Ping Pong Fucker!")

@client.command(aliases=["8ball", "eightball", "eight ball"])
async def magic_eightball(ctx, *, question):
    with open("responses.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response)

    await ctx.send(response)

client.run("MTEyOTk2NDQ4OTg5NTMxNzU2NQ.Gc28_L.7aQe3YvcVtBdj3DS8IGfo0Jx78ObNpO8hWEylQ")