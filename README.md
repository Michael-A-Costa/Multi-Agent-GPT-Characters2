# Multi Agent GPT Characters

Web app that allows 3 AI characters and a human to talk to each other using **Ollama** for local AI models and **Coqui TTS** for text-to-speech.
Originally written by DougDoug, and adapted to Local LLM and TTS by me.

This is uploaded for educational purposes. Unfortunately I don't have time to offer individual support or review pull requests, but ChatGPT or Claude can be very helpful if you are running into issues.

## Project Structure

```
Multi-Agent-GPT-Characters/
├── prompts/                    # AI personality prompts
│   ├── ai_prompts.py          # Main character prompts
│   ├── ai_prompts_generic.py  # Generic conversation prompts
│   ├── ai_prompts_murder_mystery.py  # Murder mystery scenario
│   └── ai_prompts_cold_boot.py       # Cold boot scenario
├── backup_history/            # Conversation backup files
├── samples/                   # VCTK voice samples
├── audio_in/                  # Recorded input audio
├── audio_msg/                 # Generated TTS audio
├── static/                    # Web frontend assets
├── templates/                 # HTML templates
├── multi_agent_gpt.py         # Main application
├── coqui_tts_manager.py       # TTS management
├── whisper_openai.py          # Speech-to-text
├── audio_player.py            # Audio playback
└── requirements.txt           # Python dependencies
```

## SETUP:

### 1. Python Installation

This was written in Python 3.9+. Install from: https://www.python.org/downloads/

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install PyTorch with CUDA Support (Recommended)

For better performance with Whisper speech recognition:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 4. Setup Ollama (Local AI Models)

1. Install Ollama from: https://ollama.com/
2. Pull your preferred model:
   ```bash
   ollama pull gemma3n:e4b
   # or
   ollama pull huihui_ai/deepseek-r1-abliterated:8b
   ```
3. Update the `OLLAMA_MODEL` variable in `multi_agent_gpt.py` to match your model

### 5. Setup OpenAI API (Optional - for advanced features)

- Create account at: https://platform.openai.com/
- Generate API key and set as environment variable: `OPENAI_API_KEY`

### 6. Web Interface

The app runs a Flask web server on `127.0.0.1:5151` by default. You can change this in `multi_agent_gpt.py`.

### 7. Optional: OBS Integration

First open up OBS. Make sure you're running version 28.X or later. Click Tools, then WebSocket Server Settings. Make sure "Enable WebSocket server" is checked. Then set Server Port to '4455' and set the Server Password to 'TwitchChat9'. If you use a different Server Port or Server Password in your OBS, just make sure you update the websockets_auth.py file accordingly.
Next install the Move OBS plugin: https://obsproject.com/forum/resources/move.913/ Now you can use this plugin to add a filter to an audio source that will change an image's transform based on the audio waveform. For example, I have a filter on a specific audio track that will move each agent's bell pepper icon source image whenever that pepper is talking.
Note that OBS must be open when you're running this code, otherwise OBS WebSockets won't be able to connect. If you don't need the images to move while talking, you can just delete the OBS portions of the code.

## Using the App

### 1. Configure Character Personalities

Edit the files in the `prompts/` folder to design each agent's personality and conversation purpose:

- `prompts/ai_prompts.py` - Main character definitions
- `prompts/ai_prompts_generic.py` - Generic conversation scenarios
- `prompts/ai_prompts_murder_mystery.py` - Murder mystery scenario
- `prompts/ai_prompts_cold_boot.py` - Cold boot scenario

### 2. Run the Application

```bash
python multi_agent_gpt.py
```

### 3. Interaction Modes

The application supports both **text** and **voice** input modes:

#### Text Mode (Default)

- Type your message and press Enter
- Type 'exit' to quit the application
- Agents will automatically respond and continue conversations

#### Voice Mode

Switch to voice mode by updating the `active_human_mode` variable in the code.

**Voice Controls:**

**Numpad 7 - "Talk" to the agents:**
Numpad 7 will start recording your microphone audio and automatically pause all agents. Hit Numpad 8 to stop recording. It will then transcribe your audio into text using Whisper and add your dialogue into all 3 agents' chat history. Then it will pick a random agent to "activate" and have them start talking next, resuming the conversation.

**Numpad 1/2/3 - "Activate" specific agents:**

- **Numpad 1**: Activate Agent 1
- **Numpad 2**: Activate Agent 2
- **Numpad 3**: Activate Agent 3	

These will "activate" the specified agent, meaning that agent will continue the conversation and start talking. Unless the conversation has been "paused" with F4, the activated agent will also pick a random other agent and "activate" them to talk next, so that the conversation continues indefinitely.

**F4 - "Pause" all agents:**
This stops the agents from activating each other. Basically, use this to stop the conversation from continuing any further, and then you can talk to the agents again with Numpad 7 or manually activate a specific agent with Numpad 1/2/3.

### 4. Agent Behavior

- Each agent has a unique personality and voice
- Agents automatically activate each other for continuous conversation
- All conversation history is backed up to `backup_history/` folder
- TTS audio is generated using Coqui TTS with VCTK voices

## Technical Features

### AI Models

- **Local AI**: Uses Ollama for running local language models
- **Speech Recognition**: Whisper model for speech-to-text
- **Text-to-Speech**: Coqui TTS with VCTK voice models

### Audio Processing

- Real-time audio recording and playback
- Multiple audio format support (WAV, MP3, etc.)
- Voice cloning using VCTK speaker models
- **Audio Speedup**: Generated TTS audio is automatically sped up by 1.15x (15%) for more natural conversation flow
- Configurable speedup ratio in `coqui_tts_manager.py` (default: 1.15x)

### Web Interface

- Real-time updates via WebSocket
- Visual feedback for active speakers
- Responsive design for different screen sizes

## Miscellaneous Notes

### Conversation Persistence

All agents automatically store their chat history in backup files (`backup_history/backup_history_[AGENT_NAME].txt`). When you restart the program, each agent will load from their backup file and restore the entire conversation. To reset conversations, delete the backup files.

### OBS Integration

If you want agent dialogue displayed in OBS, add a browser source and set the URL to `127.0.0.1:5151`.

### Voice Samples

The `samples/` folder contains VCTK voice samples used for TTS. You can generate additional samples using `generate_vctk_samples.py`.

### Customization

- Modify agent configurations in the `agent_configs` list
- Change TTS models and voices per agent
- Add new prompt scenarios in the `prompts/` folder
- Adjust Ollama model settings for different AI personalities
