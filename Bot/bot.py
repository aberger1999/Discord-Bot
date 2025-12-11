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
intents.voice_states = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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
    with open("Bot/response.txt", "r") as f:
        random_response = f.readlines()
        response = random.choice(random_response).strip()
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
                "width": 512,
                "height": 512,
                "num_outputs": 1
            }
        )

        # Handle the output more carefully
        try:
            # If output is already a string (URL)
            if isinstance(output, str):
                image_url = output
            # If output is a list or generator
            elif hasattr(output, '__iter__'):
                output_list = list(output)
                if output_list and len(output_list) > 0:
                    image_url = str(output_list[0])
                else:
                    await interaction.followup.send("❌ No image was generated.")
                    return
            # If output is something else
            else:
                image_url = str(output)
            
            # Get the image data
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        # Convert to Discord file
                        file = discord.File(BytesIO(data), filename="generated.png")
                        await interaction.followup.send(file=file)
                    else:
                        await interaction.followup.send(f"❌ Failed to download the generated image. Status code: {resp.status}")
        except Exception as e:
            print(f"Error processing Replicate output: {str(e)}")
            await interaction.followup.send(f"❌ Error processing the generated image: {str(e)}")

    except Exception as e:
        print(f"Error details: {str(e)}")
        await interaction.response.send_message(f"❌ An error occurred: {str(e)}")
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
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Bot is ready! Logged in as {client.user}")
    print(f"📊 Connected to {len(client.guilds)} guild(s)")

client.run(TOKEN)