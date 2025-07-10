# This code runs a thread that manages the frontend code, a thread that listens for keyboard presses from the human, and then threads for the 3 agents
# Once running, the human can activate a single agent and then let the agents continue an ongoing conversation.
# Each thread has the following core logic:

# Main Thread
    # Runs the web app

# Agent X
    # Waits to be activated
    # Once it is activated (by human or by another agent):
        # Acquire conversation lock
            # Get response from Ollama
            # Add this new response to all other agents' chat histories
        # Creates TTS with Coqui TTS
        # Acquire speaking lock (so only 1 speaks at a time)
            # Pick another thread randomly, activate them
                # Because this happens within the speaking lock, we are guaranteed that the other agents are inactive when this called.
                # But, we start this now so that the next speaker can have their answer and audio ready to go the instant this agent is done talking.
            # Update client and OBS to display stuff
            # Play the TTS audio
            # Release speaking lock (Other threads can now talk)
    
# Human Input Thread
    # Listens for input (text or voice):

    # Text Mode:
        # Wait for text input
        # Add human's response into all agents' chat history
        # Activate random agent

    # Voice Mode:
        # If Numpad 7 is pressed:
            # Toggles "pause" flag - stops other agents from activating additional agents
            # Record mic audio (until you press Numpad 8)
            # Get convo lock (but not speaking lock)
                # In theory, wait until everyone is done speaking, and because the agents are "paused" then no new ones will add to the convo
                # But to be safe, grab the convo lock to ensure that all agents HAVE to wait until my response is added into the convo history
            # Transcribe mic audio into text with Whisper
            # Add human's response into all agents' chat history
            # Release the convo lock
            # Activate random agent

        # If F4 pressed:
            # Toggles "pause" flag - stops all other agents from activating additional agents
        
        # If Numpad 1/2/3 pressed:
            # Turns off "pause" flag
            # Activates specific Agent

from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit
import threading
import time
import keyboard
import random
import logging
from rich import print
import requests
import platform
import subprocess
import signal
import re
import os
from coqui_tts_manager import CoquiTTSManager

from audio_player import AudioManager
from whisper_openai import WhisperManager
# from obs_websockets import OBSWebsocketsManager  # Uncomment to enable OBS integration
from prompts.ai_prompts import *
from prompts.ai_prompts_generic import *
from prompts.ai_prompts_murder_mystery import *
from prompts.ai_prompts_cold_boot import *

socketio = SocketIO
app = Flask(__name__)
app.config['SERVER_NAME'] = "127.0.0.1:5151"
socketio = SocketIO(app, async_mode="threading")
log = logging.getLogger('werkzeug') # Sets flask app to only print error messages, rather than all info logs
log.setLevel(logging.ERROR)

@app.route("/")
def home():
    return render_template('index.html')

@socketio.event
def connect():
    print("[green]The server connected to client!")

# Manager instances
# obswebsockets_manager = OBSWebsocketsManager()  # Uncomment to enable OBS integration
whisper_manager = WhisperManager()
coqui_manager = CoquiTTSManager()
audio_manager = AudioManager()

speaking_lock = threading.Lock()
conversation_lock = threading.Lock()

agents_paused = False

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3n:e4b"  # Change to your preferred model
BACKUP_FILE = "ChatHistoryBackup.txt"
HUMAN_NAME = "HUMAN"  # Change to your preferred human name

# Human mode switching globals
active_human_mode = "text"  # or "voice"
human_mode_lock = threading.Lock()
current_human_thread = None
current_human_agent = None

def query_ollama(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")
    except Exception as e:
        print(f"Ollama API error: {e}")
        return "Sorry, I could not get a response from the LLM."

def start_ollama_server():
    print("[cyan]Attempting to start Ollama server...")
    if platform.system() == "Windows":
        try:
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.DETACHED_PROCESS)
            print("[green]Ollama server started (Windows).")
        except Exception as e:
            print(f"Could not start Ollama server: {e}")
    else:
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[green]Ollama server started (non-Windows).")
        except Exception as e:
            print(f"Could not start Ollama server: {e}")

shutdown_event = threading.Event()

def handle_shutdown(signum, frame):
    print("[yellow]Shutdown signal received. Exiting...")
    shutdown_event.set()
    # Attempt to stop Flask server
    try:
        socketio.stop()
        print("[yellow]Flask server stopped.")
    except Exception:
        print("[red]Could not stop Flask server cleanly.")
    # Also kill Ollama processes, just like the 'exit' command
    if platform.system() == "Windows":
        print("[yellow]Killing Ollama processes (Windows)...")
        subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], shell=True)
        subprocess.run(["taskkill", "/IM", "ollama_llama_server.exe", "/F"], shell=True)
    else:
        print("[yellow]Killing Ollama processes (non-Windows)...")
        subprocess.run(["pkill", "ollama"])
        subprocess.run(["pkill", "ollama_llama_server"])
    print("[red]Force quitting process with os._exit(0)...")
    os._exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
if platform.system() == "Windows":
    # SIGBREAK is sent by Ctrl+Break on Windows
    signal.signal(signal.SIGBREAK, handle_shutdown)

# Utility function to start any bot thread
def start_bot(bot):
    bot.run()

# Function to switch human mode at runtime
def switch_human_mode(new_mode, all_agents):
    global active_human_mode, current_human_thread, current_human_agent
    with human_mode_lock:
        if new_mode == active_human_mode:
            print(f"[yellow]Already in {new_mode} mode.")
            return
        print(f"[cyan]Switching human mode to: {new_mode}")
        active_human_mode = new_mode    
        # Signal the current human agent to exit
        if current_human_agent:
            print("[yellow]Signaling current human agent to exit...")
            # The run() loop will exit when mode changes
        # Wait for the thread to finish
        if current_human_thread and current_human_thread.is_alive():
            current_human_thread.join(timeout=2)
        # Start the new human agent
        if new_mode == "text":
            current_human_agent = HumanText(f"{HUMAN_NAME}_TEXT", all_agents)
        else:
            current_human_agent = HumanVoice(f"{HUMAN_NAME}_VOICE", all_agents)
        current_human_thread = threading.Thread(target=start_bot, args=(current_human_agent,))
        current_human_thread.start()
        print(f"[green]Human agent switched to {new_mode} mode.")

# Class that represents a single AI Agent and its information
class Agent():
    
    def __init__(self, agent_name, agent_id, filter_name, all_agents, system_prompt, tts_voice, tts_model="tts_models/en/ljspeech/tacotron2-DDC"):
        print(f"[blue]Initializing Agent: {agent_name} (ID: {agent_id}, Voice: {tts_voice}, Model: {tts_model})")
        # Flag of whether this agent should begin speaking
        self.activated = False 
        # Used to identify each agent in the conversation history
        self.name = agent_name 
        # an int used to ID this agent to the frontend code
        self.agent_id = agent_id 
        # the name of the OBS filter to activate when this agent is speaking
        # You don't need to use OBS filters as part of this code, it's optional for adding extra visual flair
        self.filter_name = filter_name 
        # A list of the other agents, so that you can pick one to randomly "activate" when you finish talking
        self.all_agents = all_agents
        # The name of the txt backup file where this agent's conversation history will be stored
        backup_file_name = f"backup_history/backup_history_{agent_name}.txt"
        # Initialize the OpenAi manager with a system prompt and a file that you would like to save your conversation too
        # If the backup file isn't empty, then it will restore that backed up conversation for this agent
        self.system_prompt = f" Your real name is {self.name} " + system_prompt.get("content", "")
        print(f"[blue]Agent {self.name} will save chat history to: {backup_file_name}")
        print(f"[blue]Agent {self.name} will use system prompt: {self.system_prompt}")
        self.backup_file_name = backup_file_name
        self.chat_history = [
            {"role": "system", "content": self.system_prompt},
        ]
        self.tts_voice = tts_voice  # Store the TTS voice for the agent
        from coqui_tts_manager import CoquiTTSManager
        self.coqui_manager = CoquiTTSManager(model_name=tts_model)

    def save_chat_to_backup(self):
        with open(self.backup_file_name, "w", encoding="utf-8") as file:
            file.write(str(self.chat_history))

    def run(self):
        print(f"[blue]Agent thread started: {self.name}")
        while not shutdown_event.is_set():
            # Wait until we've been activated
            if not self.activated:
                time.sleep(0.1)
                continue
            self.activated = False
            print(f"[italic purple] {self.name} has STARTED speaking.")
            with conversation_lock:
                print(f"[grey]({self.name}) Acquired conversation lock.")
                prompt = '\n'.join([str(msg["content"]) for msg in self.chat_history])
                response = query_ollama(prompt)
                if shutdown_event.is_set():
                    print(f"[yellow]{self.name} aborting after LLM due to shutdown.")
                    break
                spoken = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
                print(f'[magenta]Got the following response:\n{spoken}')
                for agent in self.all_agents:
                    if agent is not self:
                        agent.chat_history.append({"role": "user", "content": f"[{self.name}] {spoken}"})
                        agent.save_chat_to_backup()
                self.chat_history.append({"role": "assistant", "content": spoken})
                self.save_chat_to_backup()
            # --- Activate next agent immediately after LLM, before TTS ---
            if not agents_paused:
                other_agents = [agent for agent in self.all_agents if agent is not self]
                if other_agents:
                    random_agent = random.choice(other_agents)
                    print(f"[cyan]{self.name} activating next agent: {random_agent.name}")
                    random_agent.activated = True
                else:
                    print(f"[yellow]{self.name} is the only agent, no one else to activate.")
            # --- Now do TTS and audio playback, which will block on speaking_lock ---
            import unicodedata
            def clean_tts_text(text):
                return ''.join(c for c in text if c.isascii() and c not in '*')
            cleaned_spoken = clean_tts_text(spoken)
            if len(cleaned_spoken.strip()) < 5:
                print(f'[yellow]Skipping TTS for very short or empty sentence. ({self.name})')
            else:
                if shutdown_event.is_set():
                    print(f"[yellow]{self.name} aborting before TTS due to shutdown.")
                    break
                try:
                    print(f"[blue]{self.name} generating TTS with voice '{self.tts_voice}' and model '{self.coqui_manager.tts.model_name}'...")
                    tts_file = self.coqui_manager.text_to_audio(cleaned_spoken, save_as_wave=True, speaker=self.tts_voice)
                    print(f"[green]{self.name} TTS audio generated: {tts_file}")
                except Exception as e:
                    print(f"[red]TTS failed or interrupted: {e}")
                    break
                with speaking_lock:
                    print(f"[grey]({self.name}) Acquired speaking lock.")
                    if shutdown_event.is_set():
                        print(f"[yellow]{self.name} aborting speech due to shutdown.")
                        break
                    try:
                        # OBS Integration: Activate move filter on the image (uncomment to enable)
                        # obswebsockets_manager.set_filter_visibility("Line In", self.filter_name, True)
                        
                        print(f"[blue]{self.name} playing audio...")
                        audio_manager.play_audio(tts_file, False, False, True)
                        print(f"[green]{self.name} finished audio playback.")
                    except Exception as e:
                        print(f"[red]Audio playback interrupted or failed: {e}")
                        break
                    if shutdown_event.is_set():
                        print(f"[yellow]{self.name} aborting after speech due to shutdown.")
                        break
                    socketio.emit('start_agent', {'agent_id': self.agent_id})
                    socketio.emit('agent_message', {'agent_id': self.agent_id, 'text': spoken})
                    time.sleep(1)
                    socketio.emit('clear_agent', {'agent_id': self.agent_id})
                    time.sleep(1)
                    
                    # OBS Integration: Turn off the filter (uncomment to enable)
                    # obswebsockets_manager.set_filter_visibility("Line In", self.filter_name, False)
                    
            print(f"[italic purple] {self.name} has FINISHED speaking.")
        print(f"[yellow]{self.name} thread exiting due to shutdown.")


# Class that handles human input, this thread is how you can manually activate or pause the other agents
class HumanText():
    def __init__(self, name, all_agents):
        self.name = name
        self.all_agents = all_agents
        self.chat_history = [
            {"role": "system", "content": "You are the human participant in this conversation (text mode)."},
        ]
    def run(self):
        print(f"[blue]HumanText thread started: {self.name}")
        global agents_paused, active_human_mode
        while not shutdown_event.is_set():
            if active_human_mode != "text":
                time.sleep(0.1)
                continue
            try:
                print("[blue]Waiting for your input (type 'exit' to quit)...")
                user_input = input("You: ")
            except (KeyboardInterrupt, EOFError):
                print("[yellow]Exiting chat (KeyboardInterrupt).")
                shutdown_event.set()
                break
            if user_input.strip().lower() == 'exit':
                print("[yellow]Exiting chat.")
                shutdown_event.set()
                if platform.system() == "Windows":
                    print("[yellow]Killing Ollama processes (Windows)...")
                    subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], shell=True)
                    subprocess.run(["taskkill", "/IM", "ollama_llama_server.exe", "/F"], shell=True)
                else:
                    print("[yellow]Killing Ollama processes (non-Windows)...")
                    subprocess.run(["pkill", "ollama"])
                    subprocess.run(["pkill", "ollama_llama_server"])
                break
            if user_input.strip() == '':
                print("[red]Did not receive any input!")
                continue
            with conversation_lock:
                print(f"[grey](HumanText) Acquired conversation lock.")
                for agent in self.all_agents:
                    agent.chat_history.append({"role": "user", "content": f"[{self.name}] {user_input}"})
                    agent.save_chat_to_backup()
            print(f"[italic magenta] {self.name} has FINISHED speaking.")
            agents_paused = False
            random_agent = random.randint(0, len(self.all_agents)-1)
            print(f"[cyan]Activating Agent {random_agent+1} ({self.all_agents[random_agent].name})")
            self.all_agents[random_agent].activated = True
            time.sleep(0.05)
        print("[yellow]HumanText thread exiting due to shutdown.")

class HumanVoice():
    def __init__(self, name, all_agents):
        self.name = name
        self.all_agents = all_agents
        self.chat_history = [
            {"role": "system", "content": "You are the human participant in this conversation (voice mode)."},
        ]
    def run(self):
        print(f"[blue]HumanVoice thread started: {self.name}")
        global agents_paused, active_human_mode
        while not shutdown_event.is_set():
            if active_human_mode != "voice":
                time.sleep(0.1)
                continue
            try:
                # print("[blue]Waiting for your input (press 'num 7' to start voice input, 'f4' to pause agents, or 'num 1/2/3' to activate agents)...")
                # Num 7: Start voice input (pause agents, record, transcribe, add to chat, resume, activate random agent)
                if keyboard.is_pressed('num 7'):
                    agents_paused = True
                    print(f"[italic red] Agents have been paused")
                    print(f"[italic green] {self.name} has STARTED speaking (voice input mode). Press 'num 8' to stop recording.")
                    # Force mono channel for compatibility
                    mic_audio = audio_manager.record_audio(end_recording_key='num 8', channels=1)
                    with conversation_lock:
                        transcribed_audio = whisper_manager.audio_to_text(mic_audio)
                        print(f"[teal]Got the following audio from {self.name}:\n{transcribed_audio}")
                        for agent in self.all_agents:
                            agent.chat_history.append({"role": "user", "content": f"[{self.name}] {transcribed_audio}"})
                            agent.save_chat_to_backup()
                    print(f"[italic magenta] {self.name} has FINISHED speaking (voice input mode).")
                    agents_paused = False
                    random_agent = random.randint(0, len(self.all_agents)-1)
                    print(f"[cyan]Activating Agent {random_agent+1} ({self.all_agents[random_agent].name})")
                    self.all_agents[random_agent].activated = True
                    time.sleep(1)
                # F4: Pause all agents
                elif keyboard.is_pressed('f4'):
                    print("[italic red] Agents have been paused")
                    agents_paused = True
                    time.sleep(1)
                # Num 1: Activate Agent 1
                elif keyboard.is_pressed('num 1'):
                    print("[cyan]Activating Agent 1")
                    agents_paused = False
                    self.all_agents[0].activated = True
                    time.sleep(1)
                # Num 2: Activate Agent 2
                elif keyboard.is_pressed('num 2'):
                    print("[cyan]Activating Agent 2")
                    agents_paused = False
                    self.all_agents[1].activated = True
                    time.sleep(1)
                # Num 3: Activate Agent 3
                elif keyboard.is_pressed('num 3'):
                    print("[cyan]Activating Agent 3")
                    agents_paused = False
                    self.all_agents[2].activated = True
                    time.sleep(1)
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"[red]Error in HumanVoice input thread: {e}")
                time.sleep(0.1)
        print("[yellow]HumanVoice thread exiting due to shutdown.")

if __name__ == '__main__':
    print("[bold blue]Starting Multi-Agent GPT Characters...")
    start_ollama_server()
    time.sleep(2)
    all_agents = []
    NUM_AGENTS = 3  # Change this to set the number of AIs in the conversation
    agent_configs = [
        ("OSWALD", 1, "Audio Move - Wario Pepper", VIDEOGAME_AGENT_1, "p241"),
        ("TONY KING OF NEW YORK", 2, "Audio Move - Waluigi Pepper", VIDEOGAME_AGENT_2, "p267"),
        ("VICTORIA", 3, "Audio Move - Gamer Pepper", VIDEOGAME_AGENT_3, "p243"),
    ]
    agent_threads = []
    for i in range(NUM_AGENTS):
        name, agent_id, filter_name, system_prompt, tts_voice = agent_configs[i]
        agent = Agent(name, agent_id, filter_name, all_agents, system_prompt, tts_voice, tts_model="tts_models/en/vctk/vits")
        thread = threading.Thread(target=start_bot, args=(agent,))
        agent_threads.append(thread)
        all_agents.append(agent)
        thread.start()
    # Start with only the selected human agent
    if active_human_mode == "text":
        current_human_agent = HumanText(f"{HUMAN_NAME}_TEXT", all_agents)
    else:
        current_human_agent = HumanVoice(f"{HUMAN_NAME}_VOICE", all_agents)
    current_human_thread = threading.Thread(target=start_bot, args=(current_human_agent,))
    current_human_thread.start()
    print("[italic green]!!AGENTS ARE READY TO GO!!\nType your message and press Enter, or use voice/keys if in voice mode. Type 'exit' to quit.")
    try:
        print("[blue]Starting Flask-SocketIO server...")
        socketio.run(app)
    except KeyboardInterrupt:
        print("[yellow]Flask server interrupted.")
        shutdown_event.set()
    print("[blue]Waiting for all threads to exit...")
    for thread in agent_threads:
        thread.join()
    if current_human_thread:
        current_human_thread.join()
    print("[yellow]All threads exited. Program terminated.")