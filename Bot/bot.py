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
from datetime import datetime, timedelta
from giphy_client.rest import ApiException
from googleapiclient.discovery import build
from config import TOKEN, GIPHY_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID, REPLICATE_API_KEY, GUILD_ID, OPENWEATHER_API_KEY
import requests
from dateutil import parser
from deep_translator import GoogleTranslator
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

####################################################### Bot Run ########################################################            
@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=806382276845633536))
    print("Ready!")

client.run(TOKEN)