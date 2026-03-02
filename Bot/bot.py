# Discord Bot with various commands
# Author: Alex Berger
# Date: 2023-10-01
# Description: This bot includes commands for generating images, searching for memes and GIFs, creating polls, setting reminders, and performing Google searches.
# Dependencies: discord.py, aiohttp, giphy_client, google-api-python-client, replicate, craiyon, PIL
# License: MIT
# Copyright (c) 2023 Alex Berger
##################################### Imports #####################################################
import discord, random, asyncio, re, aiohttp, giphy_client, replicate, os, math, struct, wave
from discord import app_commands, Embed
from discord.ext import commands
from typing import Optional
from io import BytesIO
from datetime import datetime, timedelta
from giphy_client.rest import ApiException
from googleapiclient.discovery import build
from config import TOKEN, GIPHY_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, REPLICATE_API_KEY, GUILD_ID, OPENWEATHER_API_KEY
import requests
from dateutil import parser
from deep_translator import GoogleTranslator
import yt_dlp
from PIL import Image, ImageDraw, ImageFont
import qrcode
######################################### Initialize clients ################################################
replicate_client = replicate.Client(api_token=REPLICATE_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Tracks users locked in a persistent server mute (user_id -> guild_id)
permamuted_users = {}

######################################### Music Queue Management ################################################
# Store music queues and voice clients for each guild
music_queues = {}
voice_clients = {}

# YT-DLP options for audio extraction
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

####################################### Magic 8Ball Command ###################################
@tree.command(name = "eightball", description = "Magic eightball", guild=discord.Object(id=GUILD_ID))
async def eightball_command(interaction, question: str):
    with open(os.path.join(os.path.dirname(__file__), "response.txt"), "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response).strip()
    await interaction.response.send_message(f"Question: {question}\nMagic 8-Ball says: {response}")

######################################### Image Generator Command ##################################################
@tree.command(name="imagine", description="Generate an image", guild=discord.Object(id=GUILD_ID))
async def imagine(interaction, prompt: str):
    """Generate an image from a text prompt using Stable Diffusion 3 via Replicate."""
    await interaction.response.defer()
    try:
        await interaction.followup.send(f"🎨 Generating image for: **{prompt}**")

        # Run Stable Diffusion 3 via Replicate (returns FileOutput objects)
        output = replicate_client.run(
            "stability-ai/stable-diffusion-3",
            input={
                "prompt": prompt,
                "output_format": "png",
                "aspect_ratio": "1:1"
            }
        )

        # Extract the image URL from the FileOutput object
        if isinstance(output, list) and len(output) > 0:
            image_url = output[0].url if hasattr(output[0], 'url') else str(output[0])
        elif hasattr(output, 'url'):
            image_url = output.url
        else:
            image_url = str(output)

        if not image_url:
            await interaction.followup.send("❌ No image was generated.")
            return

        # Download and send the image as a Discord file attachment
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    file = discord.File(BytesIO(data), filename="generated.png")
                    await interaction.followup.send(file=file)
                else:
                    await interaction.followup.send(
                        f"❌ Failed to download the generated image. (HTTP {resp.status})"
                    )

    except Exception as e:
        print(f"Imagine command error: {str(e)}")
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

######################################### Reminder Command ####################################################

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
    """Fetch a random meme from popular subreddits via meme-api.com."""
    await interaction.response.defer()

    subreddits = ['memes', 'dankmemes', 'wholesomememes']
    subreddit = random.choice(subreddits)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f'https://meme-api.com/gimme/{subreddit}') as response:
                if response.status == 200:
                    data = await response.json()

                    # Skip NSFW/spoiler posts
                    if data.get('nsfw') or data.get('spoiler'):
                        await interaction.followup.send("🔄 Got a spoiler/NSFW post — try again!")
                        return

                    embed = Embed(title=data.get('title', 'Random Meme'))
                    embed.set_image(url=data['url'])
                    embed.set_footer(text=f"From r/{data.get('subreddit', subreddit)} • 👍 {data.get('ups', 0)}")

                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Couldn't fetch a meme right now. Try again later!")

        except Exception as e:
            print(f"Meme command error: {str(e)}")
            await interaction.followup.send(f"❌ Error fetching meme: {str(e)}")

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

############################################# Weather Command ########################################################
@tree.command(name="weather", description="Get current weather for a location", guild=discord.Object(id=GUILD_ID))
async def weather(interaction, location: str):
    await interaction.response.defer()
    
    try:
        # Using OpenWeatherMap API
        api_key_weather = OPENWEATHER_API_KEY
        url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key_weather}&units=imperial"
        
        print(f"Weather API URL: {url}")  # Debug print to see the URL being used
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_data = await response.json()
                    error_message = error_data.get('message', 'Unknown error')
                    print(f"Weather API error: {error_message} (Status: {response.status})")
                    await interaction.followup.send(f"❌ Couldn't find weather data for '{location}'. Error: {error_message}")
                    return
                
                data = await response.json()
                
                # Extract weather information
                try:
                    city = data["name"]
                    country = data["sys"]["country"]
                    temp = data["main"]["temp"]
                    temp_celsius = (temp - 32) * 5/9
                    feels_like = data["main"]["feels_like"]
                    humidity = data["main"]["humidity"]
                    wind_speed = data["wind"]["speed"]
                    description = data["weather"][0]["description"]
                    icon_code = data["weather"][0]["icon"]
                    icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
                    
                    # Create embed
                    embed = Embed(
                        title=f"Weather in {city}, {country}",
                        description=f"**{description.capitalize()}**",
                        color=0x3498db
                    )
                    embed.set_thumbnail(url=icon_url)
                    embed.add_field(name="Temperature", value=f"{temp:.1f}°F / {temp_celsius:.1f}°C", inline=True)
                    embed.add_field(name="Feels Like", value=f"{feels_like:.1f}°F", inline=True)
                    embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                    embed.add_field(name="Wind Speed", value=f"{wind_speed} mph", inline=True)
                    embed.set_footer(text="Data from OpenWeatherMap")
                    
                    await interaction.followup.send(embed=embed)
                except KeyError as ke:
                    print(f"Weather data parsing error: {ke} in {data}")
                    await interaction.followup.send(f"❌ Error processing weather data for '{location}'. The API response format may have changed.")
                
    except Exception as e:
        print(f"Weather error: {str(e)}")
        await interaction.followup.send(f"❌ Error fetching weather: {str(e)}")

############################################# Joke Command ########################################################
@tree.command(name="joke", description="Get a random joke", guild=discord.Object(id=GUILD_ID))
async def joke(interaction):
    await interaction.response.defer()
    
    try:
        # Choose a random joke API
        apis = [
            "https://official-joke-api.appspot.com/random_joke",
            "https://v2.jokeapi.dev/joke/Any?safe-mode",
            "https://icanhazdadjoke.com/"
        ]
        
        api_url = random.choice(apis)
        headers = {"Accept": "application/json"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send("❌ Couldn't fetch a joke at the moment.")
                    return
                
                data = await response.json()
                
                # Format joke based on API
                if api_url == "https://official-joke-api.appspot.com/random_joke":
                    joke_text = f"**{data['setup']}**\n\n{data['punchline']}"
                elif api_url == "https://v2.jokeapi.dev/joke/Any?safe-mode":
                    if data["type"] == "single":
                        joke_text = data["joke"]
                    else:
                        joke_text = f"**{data['setup']}**\n\n{data['delivery']}"
                else:  # icanhazdadjoke
                    joke_text = data["joke"]
                
                embed = Embed(
                    title="Here's a joke for you!",
                    description=joke_text,
                    color=0xf1c40f
                )
                embed.set_footer(text="😂")
                
                await interaction.followup.send(embed=embed)
                
    except Exception as e:
        print(f"Joke error: {str(e)}")
        await interaction.followup.send(f"❌ Error fetching joke: {str(e)}")

############################################# Translator Command ########################################################
@tree.command(name="translate", description="Translate text to another language", guild=discord.Object(id=GUILD_ID))
async def translate(interaction, text: str, target_language: str):
    await interaction.response.defer()
    
    try:
        # List of supported language codes
        supported_languages = {
            "english": "en", "spanish": "es", "french": "fr", "german": "de", 
            "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja", 
            "chinese": "zh-CN", "korean": "ko", "arabic": "ar", "hindi": "hi"
        }
        
        # Convert language name to code if needed
        target_code = target_language.lower()
        if target_code in supported_languages:
            target_code = supported_languages[target_code]
        
        # Perform translation
        translator = GoogleTranslator(source='auto', target=target_code)
        translated_text = translator.translate(text)
        
        if not translated_text:
            await interaction.followup.send(f"❌ Couldn't translate to '{target_language}'. Try using a language code like 'en', 'es', 'fr', etc.")
            return
        
        embed = Embed(
            title=f"Translation to {target_language}",
            color=0x2ecc71
        )
        embed.add_field(name="Original Text", value=text, inline=False)
        embed.add_field(name="Translated Text", value=translated_text, inline=False)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Translation error: {str(e)}")
        await interaction.followup.send(f"❌ Error during translation: {str(e)}")
        
############################################# Countdown Timer Command ########################################################
@tree.command(name="countdown", description="Create a countdown to an event", guild=discord.Object(id=GUILD_ID))
async def countdown(interaction, event_name: str, date: str):
    await interaction.response.defer()
    
    try:
        # Parse the date
        try:
            target_date = parser.parse(date)
        except:
            await interaction.followup.send("❌ Invalid date format. Please use a format like 'YYYY-MM-DD' or 'MM/DD/YYYY'.")
            return
        
        # Calculate time difference
        now = datetime.now()
        if target_date < now:
            await interaction.followup.send("❌ The specified date is in the past.")
            return
        
        # Calculate time remaining
        time_diff = target_date - now
        days = time_diff.days
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Format the countdown message
        embed = Embed(
            title=f"⏰ Countdown to {event_name}",
            description=f"**Target Date:** {target_date.strftime('%A, %B %d, %Y')}",
            color=0xe74c3c
        )
        
        time_remaining = f"{days} days, {hours} hours, {minutes} minutes"
        embed.add_field(name="Time Remaining", value=time_remaining, inline=False)
        
        # Add exact date and time
        embed.set_footer(text=f"Event occurs at: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Countdown error: {str(e)}")
        await interaction.followup.send(f"❌ Error creating countdown: {str(e)}")

############################################# Word of the Day Command ########################################################
@tree.command(name="wordofday", description="Get the word of the day", guild=discord.Object(id=GUILD_ID))
async def wordofday(interaction):
    await interaction.response.defer()
    
    try:
        # Try multiple APIs with fallback options
        apis = [
            "https://random-words-api.vercel.app/word",
            "https://api.dictionaryapi.dev/api/v2/entries/en/",
            "https://www.wordnik.com/words/"
        ]
        
        # First attempt: Random Words API
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(apis[0]) as response:
                    if response.status == 200:
                        data = await response.json()
                        word = data[0]["word"]
                        definition = data[0]["definition"]
                        pronunciation = data[0].get("pronunciation", "")
                        
                        embed = Embed(
                            title=f"📚 Word of the Day: {word}",
                            color=0x1abc9c
                        )
                        
                        if pronunciation:
                            embed.add_field(name="Pronunciation", value=pronunciation, inline=False)
                            
                        embed.add_field(name="Definition", value=definition, inline=False)
                        embed.set_footer(text="Expand your vocabulary every day!")
                        
                        await interaction.followup.send(embed=embed)
                        return
            except Exception as e:
                print(f"First API failed: {str(e)}")
        
        # Fallback: Use a list of interesting words with definitions
        fallback_words = [
            {"word": "Serendipity", "definition": "The occurrence and development of events by chance in a happy or beneficial way.", "pos": "noun"},
            {"word": "Ephemeral", "definition": "Lasting for a very short time.", "pos": "adjective"},
            {"word": "Mellifluous", "definition": "Sweet or musical; pleasant to hear.", "pos": "adjective"},
            {"word": "Quintessential", "definition": "Representing the most perfect or typical example of a quality or class.", "pos": "adjective"},
            {"word": "Eloquent", "definition": "Fluent or persuasive in speaking or writing.", "pos": "adjective"},
            {"word": "Luminous", "definition": "Full of or shedding light; bright or shining.", "pos": "adjective"},
            {"word": "Resilience", "definition": "The capacity to recover quickly from difficulties; toughness.", "pos": "noun"},
            {"word": "Surreptitious", "definition": "Kept secret, especially because it would not be approved of.", "pos": "adjective"},
            {"word": "Pernicious", "definition": "Having a harmful effect, especially in a gradual or subtle way.", "pos": "adjective"},
            {"word": "Ubiquitous", "definition": "Present, appearing, or found everywhere.", "pos": "adjective"},
            {"word": "Cacophony", "definition": "A harsh, discordant mixture of sounds.", "pos": "noun"},
            {"word": "Euphoria", "definition": "A feeling or state of intense excitement and happiness.", "pos": "noun"},
            {"word": "Paradigm", "definition": "A typical example or pattern of something; a model.", "pos": "noun"},
            {"word": "Benevolent", "definition": "Well meaning and kindly.", "pos": "adjective"},
            {"word": "Enigma", "definition": "A person or thing that is mysterious, puzzling, or difficult to understand.", "pos": "noun"}
        ]
        
        # Select a random word from the fallback list
        word_data = random.choice(fallback_words)
        
        embed = Embed(
            title=f"📚 Word of the Day: {word_data['word']}",
            color=0x1abc9c
        )
        
        embed.add_field(name="Part of Speech", value=word_data["pos"], inline=True)
        embed.add_field(name="Definition", value=word_data["definition"], inline=False)
        
        # Add a fun fact about using the word
        tips = [
            "Try using this word in a conversation today!",
            "Words like this can enhance your writing.",
            "Expand your vocabulary every day!",
            "The best way to remember a word is to use it.",
            "Learning new words improves cognitive function."
        ]
        
        embed.set_footer(text=random.choice(tips))
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Word of the day error: {str(e)}")
        await interaction.followup.send(f"❌ Error fetching word of the day: {str(e)}")

############################################# Reverse Command ########################################################
@tree.command(name="reverse", description="Reverse someone's text because why not", guild=discord.Object(id=GUILD_ID))
async def reverse(interaction, text: str):
    """Reverses the given text and sends it back — surprisingly annoying."""
    reversed_text = text[::-1]

    # Zero-width characters sprinkled in so it can't be easily copy-pasted back
    trolled = "\u200b".join(reversed_text)

    embed = Embed(
        title="🔄 REVERSED",
        description=trolled,
        color=0xff6961
    )
    embed.set_footer(text=f"Original: {text}")
    await interaction.response.send_message(embed=embed)

############################################# Mock Command ##########################################################
@tree.command(name="mock", description="mOcK sOmEoNe'S tExT", guild=discord.Object(id=GUILD_ID))
async def mock(interaction, text: str):
    """Converts text to SpOnGeBoB mOcKiNg CaSe for maximum disrespect."""
    mocked = "".join(
        char.upper() if i % 2 else char.lower()
        for i, char in enumerate(text)
    )

    embed = Embed(
        description=mocked,
        color=0xf4d03f
    )
    embed.set_thumbnail(url="https://i.imgflip.com/1otk96.jpg")
    embed.set_footer(text=f"— {interaction.user.display_name} is mocking someone")
    await interaction.response.send_message(embed=embed)

############################################# Permamute Commands #####################################################
@tree.command(name="permamute", description="Permanently server-mute a user until /unpermamute is used", guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(mute_members=True)
async def permamute(interaction, target: discord.Member):
    """Locks a user into a server mute. If they unmute, the bot instantly re-mutes them."""
    if target.bot:
        await interaction.response.send_message("❌ Can't permamute a bot.", ephemeral=True)
        return

    if target.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't permamute yourself... or can you? No.", ephemeral=True)
        return

    permamuted_users[target.id] = interaction.guild_id

    # Mute them immediately if they're in a voice channel
    if target.voice and target.voice.channel:
        try:
            await target.edit(mute=True, reason=f"Permamuted by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to mute that user.", ephemeral=True)
            return

    embed = Embed(
        title="🔇 PERMAMUTED",
        description=f"{target.mention} has been **permanently server-muted**.\n"
                    f"They will be re-muted every time they try to unmute.\n\n"
                    f"Use `/unpermamute` to release them.",
        color=0xe74c3c
    )
    embed.set_footer(text=f"Muted by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="unpermamute", description="Release a user from the permamute", guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(mute_members=True)
async def unpermamute(interaction, target: discord.Member):
    """Releases a user from the permamute prison."""
    if target.id not in permamuted_users:
        await interaction.response.send_message(f"❌ {target.mention} isn't permamuted.", ephemeral=True)
        return

    del permamuted_users[target.id]

    # Unmute them if they're currently in a voice channel
    if target.voice and target.voice.channel:
        try:
            await target.edit(mute=False, reason=f"Unpermamuted by {interaction.user}")
        except discord.Forbidden:
            pass

    embed = Embed(
        title="🔊 UNPERMAMUTED",
        description=f"{target.mention} has been **released** from the permamute. They're free... for now.",
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed)

############################################# Screech Kick Command ###################################################

def _generate_screech_wav():
    """Generate a short, ear-piercing screech WAV file at bot startup."""
    filepath = os.path.join(os.path.dirname(__file__), "screech.wav")
    if os.path.exists(filepath):
        return filepath

    sample_rate = 44100
    duration = 2.5
    n_samples = int(duration * sample_rate)

    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for i in range(n_samples):
            t = i / sample_rate
            # Layer harsh high-frequency tones with a wobbling siren for maximum pain
            sample = (
                math.sin(2 * math.pi * 3000 * t) * 0.3
                + math.sin(2 * math.pi * 5500 * t) * 0.25
                + math.sin(2 * math.pi * 8000 * t) * 0.2
                + math.sin(2 * math.pi * 1200 * t * (1 + 0.5 * math.sin(2 * math.pi * 10 * t))) * 0.25
            )
            sample = max(-1.0, min(1.0, sample))
            wav_file.writeframes(struct.pack('<h', int(sample * 32767)))

    return filepath

# Pre-generate the screech file so it's ready to go
SCREECH_PATH = _generate_screech_wav()

def _find_ffmpeg():
    """Locate ffmpeg: check the system PATH first, fall back to common install locations."""
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path

    # Common Windows install locations as a fallback
    fallback_dirs = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
        r"C:\ffmpeg\bin",
        r"C:\ProgramData\chocolatey\bin",
    ]
    for directory in fallback_dirs:
        candidate = os.path.join(directory, "ffmpeg.exe")
        if os.path.isfile(candidate):
            return candidate

    return "ffmpeg"  # Last resort — hope it's on PATH at runtime

FFMPEG_PATH = _find_ffmpeg()


@tree.command(name="screechkick", description="Join VC, play an awful screech, then kick a random person", guild=discord.Object(id=GUILD_ID))
@app_commands.default_permissions(move_members=True)
async def screechkick(interaction):
    """Joins the caller's voice channel, plays an ear-piercing screech, then
    disconnects a random member from the channel."""
    await interaction.response.defer()

    # Make sure the caller is in a voice channel
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ You need to be in a voice channel to use this!", ephemeral=True)
        return

    vc_channel = interaction.user.voice.channel
    members_in_vc = [m for m in vc_channel.members if not m.bot]

    if len(members_in_vc) == 0:
        await interaction.followup.send("❌ No humans in the voice channel to kick!", ephemeral=True)
        return

    # Pick the victim before joining
    victim = random.choice(members_in_vc)

    try:
        # Connect to the voice channel
        voice_client = await vc_channel.connect()

        await interaction.followup.send(
            f"📢 **INCOMING...**\n\n"
            f"🎯 Someone in **{vc_channel.name}** is about to have a very bad time..."
        )

        # Play the screech at full volume
        audio_source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(SCREECH_PATH, executable=FFMPEG_PATH),
            volume=1.0
        )
        voice_client.play(audio_source)

        # Wait for the screech to finish playing
        while voice_client.is_playing():
            await asyncio.sleep(0.25)

        # Kick the victim from voice by disconnecting them
        try:
            await victim.move_to(None, reason="Screech-kicked by the bot")
            kick_msg = f"💀 **{victim.display_name}** got screech-kicked! Rest in peace."
        except discord.Forbidden:
            kick_msg = f"😤 Tried to kick **{victim.display_name}** but I don't have permission!"

        await interaction.followup.send(kick_msg)

        # Disconnect the bot from voice
        await voice_client.disconnect()

    except Exception as e:
        print(f"Screechkick error: {str(e)}")
        await interaction.followup.send(f"❌ Something went wrong: {str(e)}")
        # Clean up voice connection if it exists
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()

############################################# Music Commands ########################################################
def get_audio_source(url):
    """
    Extract audio from URL using yt-dlp
    
    Args:
        url: YouTube URL or direct audio URL
        
    Returns:
        tuple: (FFmpegPCMAudio source, song title) or (None, None) on error
    """
    try:
        # Extract audio information without downloading
        data = ytdl.extract_info(url, download=False)
        # Handle playlists - get first entry
        if 'entries' in data:
            data = data['entries'][0]
        # Create FFmpeg audio source from extracted URL
        return discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data.get('title', 'Unknown')
    except Exception as e:
        print(f"Error extracting audio: {str(e)}")
        return None, None

def play_next_sync(guild_id, error):
    """
    Callback function to play next song in queue (synchronous wrapper)
    This is called automatically when a song finishes playing
    
    Args:
        guild_id: Discord guild ID
        error: Error from previous playback (if any)
    """
    if error:
        print(f"Music playback error: {error}")
    
    # Check if queue exists and has songs
    if guild_id not in music_queues or not music_queues[guild_id]:
        return
    
    # Check if bot is still connected to voice channel
    if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
        return
    
    # Get next song from queue
    url, title = music_queues[guild_id].pop(0)
    source, song_title = get_audio_source(url)
    
    # Play the next song
    if source:
        voice_clients[guild_id].play(source, after=lambda e: play_next_sync(guild_id, e))
        return song_title or title
    return None

@tree.command(name="play", description="Play music from YouTube URL or search term", guild=discord.Object(id=GUILD_ID))
async def play(interaction, query: str):
    """Play music from YouTube"""
    await interaction.response.defer()
    
    # Check if user is in a voice channel
    if not interaction.user.voice:
        await interaction.followup.send("❌ You need to be in a voice channel to play music!")
        return
    
    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    
    # Connect to voice channel if not already connected
    if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
        try:
            voice_clients[guild_id] = await voice_channel.connect()
        except Exception as e:
            await interaction.followup.send(f"❌ Error connecting to voice channel: {str(e)}")
            return
    
    # Initialize queue if needed
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    
    # Determine if query is URL or search term
    if not query.startswith(('http://', 'https://')):
        query = f"ytsearch:{query}"
    
    # Extract audio info
    try:
        data = ytdl.extract_info(query, download=False)
        if 'entries' in data:
            data = data['entries'][0]
        
        url = data.get('url') or data.get('webpage_url')
        title = data.get('title', 'Unknown')
        duration = data.get('duration', 0)
        
        # Add to queue
        music_queues[guild_id].append((url, title))
        
        # If nothing is playing, start playing
        if not voice_clients[guild_id].is_playing():
            source, _ = get_audio_source(url)
            if source:
                voice_clients[guild_id].play(source, after=lambda e: play_next_sync(guild_id, e))
                
                embed = Embed(
                    title="🎵 Now Playing",
                    description=f"**{title}**",
                    color=0x1db954
                )
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
                embed.add_field(name="Queue Position", value="Now Playing", inline=True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to load audio source.")
        else:
            embed = Embed(
                title="✅ Added to Queue",
                description=f"**{title}**",
                color=0x1db954
            )
            embed.add_field(name="Position", value=f"#{len(music_queues[guild_id])}", inline=True)
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        print(f"Play error: {str(e)}")
        await interaction.followup.send(f"❌ Error playing music: {str(e)}")

@tree.command(name="pause", description="Pause the currently playing music", guild=discord.Object(id=GUILD_ID))
async def pause(interaction):
    """Pause music"""
    guild_id = interaction.guild.id
    
    if guild_id in voice_clients and voice_clients[guild_id].is_playing():
        voice_clients[guild_id].pause()
        await interaction.response.send_message("⏸️ Music paused.")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@tree.command(name="resume", description="Resume paused music", guild=discord.Object(id=GUILD_ID))
async def resume(interaction):
    """Resume music"""
    guild_id = interaction.guild.id
    
    if guild_id in voice_clients and voice_clients[guild_id].is_paused():
        voice_clients[guild_id].resume()
        await interaction.response.send_message("▶️ Music resumed.")
    else:
        await interaction.response.send_message("❌ Music is not paused.", ephemeral=True)

@tree.command(name="skip", description="Skip the current song", guild=discord.Object(id=GUILD_ID))
async def skip(interaction):
    """Skip current song"""
    guild_id = interaction.guild.id
    
    if guild_id in voice_clients and voice_clients[guild_id].is_playing():
        voice_clients[guild_id].stop()
        await interaction.response.send_message("⏭️ Skipped current song.")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@tree.command(name="queue", description="Show the music queue", guild=discord.Object(id=GUILD_ID))
async def queue(interaction):
    """Show music queue"""
    guild_id = interaction.guild.id
    
    if guild_id not in music_queues or not music_queues[guild_id]:
        await interaction.response.send_message("📭 The queue is empty.")
        return
    
    queue_list = music_queues[guild_id][:10]  # Show first 10 items
    embed = Embed(title="📋 Music Queue", color=0x1db954)
    
    queue_text = ""
    for idx, (_, title) in enumerate(queue_list, 1):
        queue_text += f"{idx}. {title}\n"
    
    if len(music_queues[guild_id]) > 10:
        queue_text += f"\n... and {len(music_queues[guild_id]) - 10} more"
    
    embed.description = queue_text or "Queue is empty"
    await interaction.response.send_message(embed=embed)

@tree.command(name="stop", description="Stop music and clear queue", guild=discord.Object(id=GUILD_ID))
async def stop(interaction):
    """Stop music and clear queue"""
    guild_id = interaction.guild.id
    
    if guild_id in voice_clients and voice_clients[guild_id].is_connected():
        voice_clients[guild_id].stop()
        if guild_id in music_queues:
            music_queues[guild_id].clear()
        await interaction.response.send_message("🛑 Music stopped and queue cleared.")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@tree.command(name="leave", description="Make the bot leave the voice channel", guild=discord.Object(id=GUILD_ID))
async def leave(interaction):
    """Leave voice channel"""
    guild_id = interaction.guild.id
    
    if guild_id in voice_clients and voice_clients[guild_id].is_connected():
        await voice_clients[guild_id].disconnect()
        if guild_id in music_queues:
            music_queues[guild_id].clear()
        del voice_clients[guild_id]
        await interaction.response.send_message("👋 Left the voice channel.")
    else:
        await interaction.response.send_message("❌ I'm not in a voice channel.", ephemeral=True)

############################################# Meme Generator Command ########################################################
@tree.command(name="memegen", description="Generate a meme with custom text", guild=discord.Object(id=GUILD_ID))
async def memegen(interaction, top_text: str, bottom_text: Optional[str] = None, template: Optional[str] = None):
    """Generate a meme with custom text"""
    await interaction.response.defer()
    
    try:
        # Popular meme templates
        templates = {
            "drake": "https://i.imgflip.com/30b1gx.jpg",
            "distracted": "https://i.imgflip.com/1ur9b0.jpg",
            "doge": "https://i.imgflip.com/4t0m5.jpg",
            "expanding": "https://i.imgflip.com/26am.jpg",
            "change": "https://i.imgflip.com/24y43o.jpg",
            "button": "https://i.imgflip.com/1g8my4.jpg",
            "this": "https://i.imgflip.com/261o3j.jpg",
            "patrick": "https://i.imgflip.com/26am.jpg",
            "roll": "https://i.imgflip.com/1bhk.jpg",
            "tuxedo": "https://i.imgflip.com/30b1gx.jpg"
        }
        
        # Use default template if not specified
        if not template or template.lower() not in templates:
            template_url = templates["drake"]
        else:
            template_url = templates[template.lower()]
        
        # Download template image
        async with aiohttp.ClientSession() as session:
            async with session.get(template_url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Failed to load meme template.")
                    return
                
                img_data = await resp.read()
                img = Image.open(BytesIO(img_data))
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                draw = ImageDraw.Draw(img)
                
                # Try to load a font, fallback to default if not available
                try:
                    # Try to use a system font
                    font_size = 40
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                except:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
                    except:
                        font = ImageFont.load_default()
                
                # Get image dimensions
                width, height = img.size
                
                # Draw top text
                if top_text:
                    # Calculate text position (centered)
                    bbox = draw.textbbox((0, 0), top_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (width - text_width) // 2
                    y = 20
                    
                    # Draw text with outline (stroke)
                    draw.text((x-2, y-2), top_text, font=font, fill='black')
                    draw.text((x+2, y-2), top_text, font=font, fill='black')
                    draw.text((x-2, y+2), top_text, font=font, fill='black')
                    draw.text((x+2, y+2), top_text, font=font, fill='black')
                    draw.text((x, y), top_text, font=font, fill='white')
                
                # Draw bottom text
                if bottom_text:
                    bbox = draw.textbbox((0, 0), bottom_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    x = (width - text_width) // 2
                    y = height - text_height - 20
                    
                    # Draw text with outline
                    draw.text((x-2, y-2), bottom_text, font=font, fill='black')
                    draw.text((x+2, y-2), bottom_text, font=font, fill='black')
                    draw.text((x-2, y+2), bottom_text, font=font, fill='black')
                    draw.text((x+2, y+2), bottom_text, font=font, fill='black')
                    draw.text((x, y), bottom_text, font=font, fill='white')
                
                # Save to bytes
                output = BytesIO()
                img.save(output, format='PNG')
                output.seek(0)
                
                # Send as file
                file = discord.File(output, filename="meme.png")
                await interaction.followup.send(file=file)
                
    except Exception as e:
        print(f"Meme generator error: {str(e)}")
        await interaction.followup.send(f"❌ Error generating meme: {str(e)}")

############################################# Urban Dictionary Command ########################################################
@tree.command(name="urban", description="Look up a word on Urban Dictionary", guild=discord.Object(id=GUILD_ID))
async def urban(interaction, word: str):
    """Look up word on Urban Dictionary"""
    await interaction.response.defer()
    
    try:
        url = f"https://api.urbandictionary.com/v0/define?term={word}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await interaction.followup.send(f"❌ Couldn't fetch definition for '{word}'.")
                    return
                
                data = await response.json()
                
                if not data.get('list'):
                    await interaction.followup.send(f"❌ No definition found for '{word}'.")
                    return
                
                # Get the top definition
                definition = data['list'][0]
                
                embed = Embed(
                    title=f"📖 {definition['word']}",
                    description=definition['definition'][:2000],  # Discord limit
                    color=0xff6b6b
                )
                
                if definition.get('example'):
                    embed.add_field(
                        name="Example",
                        value=definition['example'][:1000],
                        inline=False
                    )
                
                embed.add_field(name="👍", value=definition.get('thumbs_up', 0), inline=True)
                embed.add_field(name="👎", value=definition.get('thumbs_down', 0), inline=True)
                embed.set_footer(text="Powered by Urban Dictionary")
                
                await interaction.followup.send(embed=embed)
                
    except Exception as e:
        print(f"Urban Dictionary error: {str(e)}")
        await interaction.followup.send(f"❌ Error fetching definition: {str(e)}")

############################################# Random Fact Command ########################################################
@tree.command(name="fact", description="Get a random interesting fact", guild=discord.Object(id=GUILD_ID))
async def fact(interaction):
    """Get a random fact"""
    await interaction.response.defer()
    
    try:
        # Try multiple fact APIs
        apis = [
            "https://uselessfacts.jsph.pl/random.json?language=en",
            "https://api.api-ninjas.com/v1/facts",
        ]
        
        async with aiohttp.ClientSession() as session:
            # Try first API
            try:
                async with session.get(apis[0]) as response:
                    if response.status == 200:
                        data = await response.json()
                        fact_text = data.get('text', '')
                        
                        embed = Embed(
                            title="💡 Random Fact",
                            description=fact_text,
                            color=0x3498db
                        )
                        await interaction.followup.send(embed=embed)
                        return
            except:
                pass
            
            # Fallback to hardcoded facts
            facts = [
                "Octopuses have three hearts!",
                "A group of flamingos is called a 'flamboyance'.",
                "Bananas are berries, but strawberries aren't.",
                "Honey never spoils. You could eat 3000-year-old honey!",
                "A day on Venus is longer than its year.",
                "Sharks have been around longer than trees.",
                "Wombat poop is cube-shaped.",
                "There are more possible games of chess than atoms in the observable universe.",
                "A single cloud can weigh more than a million pounds.",
                "Dolphins have names for each other.",
                "The human brain uses about 20% of the body's total energy.",
                "A group of owls is called a 'parliament'.",
                "The speed of light is about 186,282 miles per second.",
                "There are more stars in the universe than grains of sand on all beaches on Earth.",
                "The Great Wall of China is not visible from space with the naked eye."
            ]
            
            fact_text = random.choice(facts)
            embed = Embed(
                title="💡 Random Fact",
                description=fact_text,
                color=0x3498db
            )
            await interaction.followup.send(embed=embed)
            
    except Exception as e:
        print(f"Fact error: {str(e)}")
        await interaction.followup.send(f"❌ Error fetching fact: {str(e)}")

############################################# QR Code Generator Command ########################################################
@tree.command(name="qrcode", description="Generate a QR code from text", guild=discord.Object(id=GUILD_ID))
async def qrcode_cmd(interaction, text: str):
    """Generate QR code"""
    await interaction.response.defer()
    
    try:
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        
        # Send as file
        file = discord.File(output, filename="qrcode.png")
        embed = Embed(
            title="📱 QR Code Generated",
            description=f"**Content:** {text[:100]}",
            color=0x000000
        )
        embed.set_image(url="attachment://qrcode.png")
        
        await interaction.followup.send(embed=embed, file=file)
        
    except Exception as e:
        print(f"QR code error: {str(e)}")
        await interaction.followup.send(f"❌ Error generating QR code: {str(e)}")

####################################################### Bot Run ########################################################
@client.event
async def on_voice_state_update(member, before, after):
    """Re-mutes permamuted users whenever they try to unmute themselves."""
    if member.id not in permamuted_users:
        return

    if permamuted_users[member.id] != member.guild.id:
        return

    # If they just joined or unmuted in a voice channel, slam the mute back on
    if after.channel is not None and not after.mute:
        try:
            await member.edit(mute=True, reason="Permamuted — nice try")
        except discord.Forbidden:
            pass

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is ready! Logged in as {client.user}")
    print(f"📊 Connected to {len(client.guilds)} guild(s)")

client.run(TOKEN)