# Discord Bot with Slash Commands (discord.py 2.x)

A production-ready Discord bot project optimized for deployment on Railway, built with `discord.py` 2.x and utilizing slash commands (app_commands).

## Features

1. **`/setup`**: (Admin only) Automatically sets up a structured server layout with:
   - "TEXT CHANNELS" Category
   - "VOICE CHANNELS" Category
   - Customizable number of Text and Voice Channels (Default: 20 each)
2. **`/ping`**: Checks bot latency.
3. **`/serverinfo`**: Returns detailed statistics about the current server (members, channels, owner, roles, etc.).

---

## 🛠️ Step-by-Step Local Setup Instructions (For Beginners)

### Step 1: Create a Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and give your bot a name.
3. Navigate to the **Bot** tab on the left.
4. Click **Add Bot** and confirm.
5. Under the Bot token section, click **Reset Token** and copy the new token. Save it somewhere secure.
6. Enable the **Guild Members Intent** if you want correct member information, although basic information will work fine with default intents.

### Step 2: Invite the Bot to Your Server
1. Go to the **OAuth2** tab, then select **URL Generator**.
2. Under **Scopes**, select `bot` and `applications.commands`.
3. Under **Bot Permissions**, check **Administrator** (required for `/setup`).
4. Copy the generated URL at the bottom and open it in your browser to invite the bot to your server.

### Step 3: Local Installation
1. Ensure you have Python 3.8 or higher installed on your computer.
2. Clone or download this project folder.
3. Open your terminal or command prompt inside the project directory.
4. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   ```
5. Activate the virtual environment:
   - **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
   - **macOS/Linux:** `source venv/bin/activate`
6. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Step 4: Configure the Bot Environment
1. Copy the `.env.example` file and rename the copy to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file and replace `YOUR_TOKEN_HERE` with your copied Discord Bot Token:
   ```env
   TOKEN=your_actual_discord_bot_token_here
   ```

### Step 5: Run the Bot Locally
1. Start the bot by running:
   ```bash
   python main.py
   ```
2. The console will display a log confirming the sync of commands:
   ```text
   Successfully synced 3 application commands globally.
   Bot is active and ready to process slash commands.
   ```

---

## 🚀 How to Deploy on Railway

1. **Push your code to GitHub**: Create a repository on GitHub and push all project files (including the `Procfile` and `requirements.txt`).
2. **Create a Railway Account**: Sign up at [Railway.app](https://railway.app/).
3. **Start a New Project**:
   - Click **New Project** -> **Deploy from GitHub repo**.
   - Select your Discord bot repository.
4. **Add Variables**:
   - In your Railway project, navigate to the **Variables** tab.
   - Add the following environment variable:
     - **Key**: `TOKEN`
     - **Value**: `[Your Discord Bot Token]`
5. **Deployment**:
   - Railway will automatically detect the Python environment and run the command specified in your `Procfile` (`worker: python main.py`).
   - The deployment will spin up a background worker that keeps the bot online 24/7.
