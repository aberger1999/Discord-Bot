import discord
from discord import app_commands
from discord.ext import commands
import random
from stylegan2_pytorch import StyleGAN2

'''def run_discord_bot():
    TOKEN = 'TOKEN'
    client = discord.Client()

    @client.event
    async def on_ready():
        print(f'{client.user} is now running!')

    client.run(TOKEN)'''

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
TOKEN = ""

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


@tree.comand(name = "generate", description = "Generate images", guild=discord.Object(id=806382276845633536))
async def generate_command(interaction, input: str):
    def generate_image(pic: str):
        model = StyleGAN2()
        image = model(pic)
        return image
    generated_image = generate_image(input)
    await interaction.response.send_message(content="Generated image:", file=discord.File(generated_image, 'generated_image.png'))

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=806382276845633536))
    print("Ready!")


client.run(TOKEN)


