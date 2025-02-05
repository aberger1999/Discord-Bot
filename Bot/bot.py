# Discord Bot with various commands
# Author: Alex Berger
# Date: 2023-10-01
# Description: This bot includes commands for generating images, searching for memes and GIFs, creating polls, setting reminders, and performing Google searches.
# Dependencies: discord.py, aiohttp, giphy_client, google-api-python-client, replicate, craiyon, PIL
# License: MIT
# Copyright (c) 2023 Alex Berger
##################################### Imports #####################################################
import discord, random, asyncio, re, aiohttp, giphy_client, replicate, os
from discord import app_commands, Embed
from typing import Optional
from io import BytesIO
from datetime import datetime
from giphy_client.rest import ApiException
from googleapiclient.discovery import build
from config import TOKEN, GIPHY_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, REPLICATE_API_KEY, GUILD_ID
######################################### Initialize clients ################################################
replicate_client = replicate.Client(api_token=REPLICATE_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

####################################### Magic 8Ball Command ###################################
@tree.command(name = "eightball", description = "Magic eightball", guild=discord.Object(id=GUILD_ID))
async def eightball_command(interaction, question: str):
    with open("discordbot/response.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response)
    await interaction.response.send_message(f"Question: {question}\nMagic 8-Ball says: {response}")

######################################### Image Generator Command ##################################################
@tree.command(name="imagine", description="Generate an image", guild=discord.Object(id=GUILD_ID))
async def imagine(interaction, prompt: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send(f"🎨 Generating image for: {prompt}")
        
        # Run the model using the global client
        output = replicate_client.run(
            "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
            input={
                "prompt": prompt,
                "image_dimensions": "512x512",
                "num_outputs": 1
            }
        )

        # Get the image URL
        output_list = list(output)
        if output_list and len(output_list) > 0:
            image_url = output_list[0]
            
            # Get the image data
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        # Convert to Discord file
                        file = discord.File(BytesIO(data), filename="generated.png")
                        await interaction.followup.send(file=file)
                    else:
                        await interaction.followup.send("❌ Failed to download the generated image.")
        else:
            await interaction.followup.send("❌ No image was generated.")

    except Exception as e:
        print(f"Error details: {str(e)}")
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")
##################################### Poll Command ##############################################

@tree.command(name="poll", description="Create a poll with 2-5 options", guild=discord.Object(id=GUILD_ID))
async def poll(interaction, question: str, option1: str, option2: str, 
               option3: Optional[str] = None, option4: Optional[str] = None, option5: Optional[str] = None):
    # List of emojis for reactions
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    # Create poll message
    poll_content = f"📊 **Poll: {question}**\n\n"
    options = [opt for opt in [option1, option2, option3, option4, option5] if opt is not None]
    
    for idx, option in enumerate(options):
        poll_content += f"{emojis[idx]} {option}\n"
    
    await interaction.response.send_message(poll_content)
    message = await interaction.original_response()
    
    # Add reactions
    for idx in range(len(options)):
        await message.add_reaction(emojis[idx])

####################################### Reminder Command ####################################################

# Store active reminders
active_reminders = {}

def parse_time(time_str):
    """Convert time string (e.g., '1h30m', '45m', '2h') to seconds"""
    total_seconds = 0
    pattern = re.compile(r'(\d+)([hm])')
    matches = pattern.findall(time_str)
    
    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
    
    return total_seconds

@tree.command(name="remind", description="Set a reminder (format: 1h30m, 45m, 2h)", guild=discord.Object(id=GUILD_ID))
async def remind(interaction, time: str, reminder: str):
    try:
        seconds = parse_time(time)
        if seconds <= 0:
            raise ValueError("Invalid time format")
        
        await interaction.response.send_message(
            f"✅ I'll remind you about: '{reminder}' in {time}"
        )
        
        # Schedule the reminder
        async def send_reminder():
            await asyncio.sleep(seconds)
            try:
                await interaction.user.send(
                    f"⏰ **Reminder:** {reminder}\n"
                    f"*(Set {time} ago)*"
                )
            except discord.Forbidden:
                # If DM is blocked, try to send to the original channel
                channel = interaction.channel
                await channel.send(
                    f"⏰ {interaction.user.mention}, here's your reminder: {reminder}"
                )
        
        # Store and start the reminder
        reminder_task = asyncio.create_task(send_reminder())
        active_reminders[f"{interaction.user.id}_{datetime.now().timestamp()}"] = reminder_task
        
    except ValueError as e:
        await interaction.response.send_message(
            "❌ Invalid time format! Please use combinations of hours and minutes (e.g., 1h30m, 45m, 2h)",
            ephemeral=True
        )


####################################### Meme/GIF Command ########################################################
@tree.command(name="gif", description="Search for a GIF", guild=discord.Object(id=GUILD_ID))
async def gif(interaction, search_term: str):
    await interaction.response.defer()
    
    try:
        # Create giphy instance
        api_instance = giphy_client.DefaultApi()
        
        # Search for GIF
        api_response = api_instance.gifs_search_get(
            GIPHY_API_KEY,
            search_term,
            limit=5,
            rating='g'
        )
        
        if api_response.data:
            # Get random GIF from results
            gif_choice = random.choice(api_response.data)
            gif_url = gif_choice.images.original.url
            
            # Create embed
            embed = Embed(title=f"GIF: {search_term}")
            embed.set_image(url=gif_url)
            embed.set_footer(text="Powered by GIPHY")
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Couldn't find any GIFs for '{search_term}'")
            
    except ApiException as e:
        await interaction.followup.send(f"Error: {str(e)}")


@tree.command(name="meme", description="Get a random meme", guild=discord.Object(id=GUILD_ID))
async def meme(interaction):
    await interaction.response.defer()
    
    subreddits = ['memes', 'dankmemes', 'wholesomememes']
    subreddit = random.choice(subreddits)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'https://www.reddit.com/r/{subreddit}/hot.json?limit=50') as response:
                if response.status == 200:
                    data = await response.json()
                    posts = [post['data'] for post in data['data']['children'] 
                            if not post['data']['is_self'] and 
                            post['data']['url'].endswith(('.jpg', '.png', '.gif'))]
                    
                    if posts:
                        random_post = random.choice(posts)
                        
                        # Create embed
                        embed = Embed(title=random_post['title'])
                        embed.set_image(url=random_post['url'])
                        embed.set_footer(text=f"From r/{subreddit}")
                        
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send("Couldn't find any memes at the moment.")
                else:
                    await interaction.followup.send("Error fetching meme.")
                    
        except Exception as e:
            await interaction.followup.send(f"Error: {str(e)}")

######################################## Google Search Command ###################################################
# Google Search Command
@tree.command(name="search", description="Quick Google search", guild=discord.Object(id=GUILD_ID))
async def search(interaction, query: str):
    await interaction.response.defer()
    
    try:
        # Create Google Custom Search service
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        
        # Perform search
        result = service.cse().list(
            q=query,
            cx=GOOGLE_CSE_ID,
            num=3  # Number of results to return
        ).execute()
        
        if 'items' in result:
            response = "**Search Results:**\n\n"
            for item in result['items']:
                response += f"**{item['title']}**\n"
                response += f"{item['snippet']}\n"
                response += f"🔗 {item['link']}\n\n"
            
            await interaction.followup.send(response)
        else:
            await interaction.followup.send(f"No results found for '{query}'")
            
    except Exception as e:
        await interaction.followup.send(f"Error performing search: {str(e)}")

############################################# Music Command ########################################################


####################################################### Bot Run ########################################################            

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=806382276845633536))
    print("Ready!")

client.run(TOKEN)