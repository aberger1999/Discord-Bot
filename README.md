# Discord Bot

A feature-rich Discord bot built with Python and discord.py. This bot includes various fun and useful commands for entertainment, information, and productivity.

## Features

### 🎵 Music Commands
- **`/play [query]`** - Play music from YouTube (supports URLs or search terms)
- **`/pause`** - Pause the currently playing music
- **`/resume`** - Resume paused music
- **`/skip`** - Skip the current song
- **`/queue`** - View the music queue
- **`/stop`** - Stop music and clear the queue
- **`/leave`** - Make the bot leave the voice channel

### 🎨 Image & Meme Commands
- **`/imagine [prompt]`** - Generate AI images using Stable Diffusion
- **`/meme`** - Get a random meme from Reddit
- **`/gif [search_term]`** - Search for GIFs using GIPHY
- **`/memegen [top_text] [bottom_text] [template]`** - Generate custom memes with text overlays

### 🔍 Information Commands
- **`/search [query]`** - Quick Google search
- **`/weather [location]`** - Get current weather for a location
- **`/urban [word]`** - Look up a word on Urban Dictionary
- **`/fact`** - Get a random interesting fact
- **`/wordofday`** - Get the word of the day with definition

### 🎮 Fun Commands
- **`/eightball [question]`** - Ask the Magic 8-Ball a question
- **`/joke`** - Get a random joke
- **`/poll [question] [options...]`** - Create a poll with 2-5 options
- **`/countdown [event_name] [date]`** - Create a countdown to an event

### 🛠️ Utility Commands
- **`/remind [time] [reminder]`** - Set a reminder (format: 1h30m, 45m, 2h)
- **`/translate [text] [target_language]`** - Translate text to another language
- **`/qrcode [text]`** - Generate a QR code from text

## Setup

### Prerequisites
- Python 3.9 or higher
- FFmpeg (required for music functionality)
- Discord Bot Token
- API Keys (see Configuration section)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Discord-Bot
```

2. Create a virtual environment:
```bash
python3 -m venv venvdiscord
source venvdiscord/bin/activate  # On Windows: venvdiscord\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install FFmpeg:
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt install ffmpeg`
   - **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html)

### Configuration

1. Create a Discord bot application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Get your bot token and invite the bot to your server
3. Edit `Bot/config.py` and add your API keys:

```python
TOKEN = 'your-discord-bot-token'
GIPHY_API_KEY = 'your-giphy-api-key'  # Get from https://developers.giphy.com/
GOOGLE_API_KEY = 'your-google-api-key'  # Get from Google Cloud Console
GOOGLE_CSE_ID = 'your-custom-search-engine-id'  # Create at https://programmablesearchengine.google.com/
REPLICATE_API_KEY = 'your-replicate-api-key'  # Get from https://replicate.com/
OPENWEATHER_API_KEY = 'your-openweather-api-key'  # Get from https://openweathermap.org/api
GUILD_ID = 'your-guild-id'  # Your Discord server ID
```

### Running the Bot

```bash
cd Bot
python bot.py
```

## Dependencies

- `discord.py` - Discord API wrapper
- `aiohttp` - Async HTTP client
- `giphy-client` - GIPHY API client
- `Pillow` - Image processing
- `google-api-python-client` - Google API client
- `yt-dlp` - YouTube audio extraction
- `PyNaCl` - Voice support
- `deep-translator` - Translation service
- `python-dateutil` - Date parsing
- `replicate` - AI image generation
- `qrcode[pil]` - QR code generation

## Notes

- The bot uses slash commands, so make sure your Discord server supports them
- Music functionality requires FFmpeg to be installed and accessible in your PATH
- Some features require internet connectivity and valid API keys
- The bot is configured for a specific guild (server) - modify `GUILD_ID` in `config.py` to change this

## License

MIT License - Copyright (c) 2023 Alex Berger
