import discord, random, base64, asyncio, re, aiohttp, giphy_client
from discord import app_commands, InteractionResponse, Embed
from discord.ext import commands
from craiyon import Craiyon, craiyon_utils
from io import BytesIO
from PIL import Image
from datetime import datetime
from giphy_client.rest import ApiException
from googleapiclient.discovery import build
from Bot.config import TOKEN, GIPHY_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

####################################### Magic 8Ball Command ###################################
@tree.command(name = "eightball", description = "Magic eightball", guild=discord.Object(id=806382276845633536))
async def eightball_command(interaction, question: str):
    with open("discordbot/response.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response)
    await interaction.response.send_message(f"Question: {question}\nMagic 8-Ball says: {response}")

######################################### Image Generator Command ##################################################
generator = Craiyon()  # initialize Craiyon class

@tree.command(name="imagine", description="Generate images based on a prompt", guild=discord.Object(id=806382276845633536))
async def imagine(interaction, prompt: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send(f"🎨 Generating image for: {prompt}...")
        
        if len(prompt) > 100:
            raise ValueError("Prompt is too long. Maximum allowed length is 100 characters.")

        print(f"Debug - Starting generation for prompt: {prompt}")
        generator = Craiyon()  # Create new instance for each request
        
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: generator.generate(prompt)
            )
            print(f"Debug - API Response received: {result}")
        except Exception as api_error:
            print(f"Debug - API Error: {str(api_error)}")
            raise ValueError("Failed to connect to image generation service. Please try again later.")

        if not result or not hasattr(result, 'images'):
            raise ValueError("No images were generated. Please try a different prompt.")

        try:
            images = craiyon_utils.encode_base64(result.images)
            print(f"Debug - Number of images received: {len(images)}")
            
            # Only process the first image
            image_bytes = base64.b64decode(images[0])
            image = Image.open(BytesIO(image_bytes))

            with BytesIO() as image_io:
                image.save(image_io, format="PNG")
                image_io.seek(0)
                await interaction.followup.send(file=discord.File(image_io, filename="result.png"))

        except Exception as img_error:
            print(f"Debug - Image Processing Error: {str(img_error)}")
            raise ValueError("Error processing the generated image. Please try again.")

    except ValueError as ve:
        await interaction.followup.send(content=f"❌ {str(ve)}")
    except Exception as e:
        print(f"Debug - Unexpected Error: {type(e).__name__}: {str(e)}")
        await interaction.followup.send(content="❌ An unexpected error occurred. Please try again later.")
##################################### Poll Command ##############################################

@tree.command(name="poll", description="Create a poll with 2-5 options", guild=discord.Object(id=806382276845633536))
async def poll(interaction, question: str, option1: str, option2: str, 
               option3: str = None, option4: str = None, option5: str = None):
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

@tree.command(name="remind", description="Set a reminder (format: 1h30m, 45m, 2h)", guild=discord.Object(id=806382276845633536))
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
@tree.command(name="gif", description="Search for a GIF", guild=discord.Object(id=806382276845633536))
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


@tree.command(name="meme", description="Get a random meme", guild=discord.Object(id=806382276845633536))
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
@tree.command(name="search", description="Quick Google search", guild=discord.Object(id=806382276845633536))
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