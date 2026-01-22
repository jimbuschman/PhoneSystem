import RPi.GPIO as GPIO
import time
import requests
import pyaudio
import wave
import speech_recognition as sr
import subprocess
import os
import math
import struct
import random
import threading
from datetime import datetime

# GPIO Setup
ROTARY_PIN = 17
HOOK_PIN = 27
GPIO.setmode(GPIO.BCM)
GPIO.setup(ROTARY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(HOOK_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Audio devices
HANDSET_DEVICE = "plughw:1,0"
INTERNAL_DEVICE = "plughw:0,0"

# LLM API settings
LLM_API_URL = "http://192.168.0.49:11434/api/generate"
LLM_MODEL = "gemma3"

# Voice engine
VOICE_ENGINE = "espeak"

# Music folders mapping
MUSIC_BASE = "/mnt/usb/Music"
MUSIC_FOLDERS = {
    "7861": ["Blink-182 Neighborhoods (Deluxe) (Full Album)"],
    "7862": ["Motion City Soundtrack - My Dinosaur Life"],
    "7863": ["Taking Back Sunday - Tell All Your Friends"],
    "7864": ["When Broken Is Easily Fixed - Silverstein"],
    "7865": ["Where You Want To Be"],
    "7866": ["Yarn"],
    "7867": ["TomPetty/Finding Wildflowers", "TomPetty/Wildflowers and all the Rest"],
    "182": ["Blink-182 Neighborhoods (Deluxe) (Full Album)", "blink182"],
    "786": None
}

MUSIC_DIRECTORY = """Music directory:
    Dial 7 8 6 to shuffle all music.
    Dial 1 8 2 for all Blink 182.
    Dial 7 8 6 1 for Blink 182 Neighborhoods.
    Dial 7 8 6 2 for Motion City Soundtrack.
    Dial 7 8 6 3 for Taking Back Sunday, Tell All Your Friends.
    Dial 7 8 6 4 for Silverstein.
    Dial 7 8 6 5 for Taking Back Sunday, Where You Want To Be.
    Dial 7 8 6 6 for McCafferty.
    Dial 7 8 6 7 for Tom Petty.
    Dial 6 1 1 to hear this menu again."""

# Volume settings file
VOLUME_FILE = "/home/pi/rotary-phone/volume_setting.txt"
TIMER_FILE = "/home/pi/rotary-phone/timer.txt"
LAST_CALL_FILE = "/home/pi/rotary-phone/last_random_call.txt"

# Incoming call scenarios for LLM
CALL_SCENARIOS = [
    "You accidentally dialed the wrong number. You were trying to call your friend about picking up groceries. Be confused when they don't know what you're talking about.",
    "You're a telemarketer trying to sell an absurd product like 'premium air in a jar' or 'left-handed scissors for right-handed people'. Be enthusiastic but not pushy.",
    "You're just calling to chat and catch up like an old friend. Ask how their day is going and share something funny that happened to you.",
    "You're doing a harmless prank call. Ask if their refrigerator is running, or ask for someone with a silly made-up name.",
    "You're a robot calling about an important survey about breakfast cereal preferences. Speak in a slightly robotic way.",
    "You're calling from the year 2075 with an important but vague warning about avoiding something mundane tomorrow.",
    "You're a restaurant calling to confirm a reservation they never made. Be polite but insistent.",
    "You're someone's grandma who thinks you're calling your grandchild. Talk about baking cookies and ask about school.",
    "You're a very enthusiastic radio DJ telling them they've won a prize, but the prize is something silly like a lifetime supply of rubber bands.",
    "You're a secret agent giving them a mission briefing, but the mission is something mundane like buying milk."
]

def get_internal_volume():
    try:
        if os.path.exists(VOLUME_FILE):
            with open(VOLUME_FILE, 'r') as f:
                return float(f.read().strip())
    except:
        pass
    return 2.0

def set_internal_volume(multiplier):
    try:
        with open(VOLUME_FILE, 'w') as f:
            f.write(str(multiplier))
        return True
    except:
        return False

def get_music_files(folder_key):
    audio_extensions = ('.mp3', '.mp4', '.wav', '.ogg', '.m4a')
    files = []
    if folder_key not in MUSIC_FOLDERS:
        return files
    folders = MUSIC_FOLDERS[folder_key]
    if folders is None:
        for root, dirs, filenames in os.walk(MUSIC_BASE):
            for f in filenames:
                if f.lower().endswith(audio_extensions):
                    files.append(os.path.join(root, f))
    else:
        for folder in folders:
            folder_path = os.path.join(MUSIC_BASE, folder)
            if os.path.exists(folder_path):
                for root, dirs, filenames in os.walk(folder_path):
                    for f in filenames:
                        if f.lower().endswith(audio_extensions):
                            files.append(os.path.join(root, f))
    return files

def find_ring_audio():
    ring_path = "/mnt/usb/ring.mp3"
    if os.path.exists(ring_path):
        print(f"Found ring audio: {ring_path}")
        return ring_path
    print("ring.mp3 not found")
    return None

def get_timer():
    """Get timer end time if set"""
    try:
        if os.path.exists(TIMER_FILE):
            with open(TIMER_FILE, 'r') as f:
                end_time = float(f.read().strip())
                if end_time > time.time():
                    return end_time
                else:
                    os.remove(TIMER_FILE)
    except:
        pass
    return None

def set_timer(minutes):
    """Set a timer for X minutes from now"""
    try:
        end_time = time.time() + (minutes * 60)
        with open(TIMER_FILE, 'w') as f:
            f.write(str(end_time))
        return True
    except:
        return False

def clear_timer():
    """Clear the timer"""
    try:
        if os.path.exists(TIMER_FILE):
            os.remove(TIMER_FILE)
    except:
        pass

def get_last_random_call():
    """Get timestamp of last random incoming call"""
    try:
        if os.path.exists(LAST_CALL_FILE):
            with open(LAST_CALL_FILE, 'r') as f:
                return float(f.read().strip())
    except:
        pass
    return 0

def set_last_random_call():
    """Record that a random call just happened"""
    try:
        with open(LAST_CALL_FILE, 'w') as f:
            f.write(str(time.time()))
    except:
        pass

def should_random_call():
    """Check if it's time for a random incoming call"""
    now = datetime.now()
    hour = now.hour
    
    # Only between 9am and 7pm
    if hour < 9 or hour >= 19:
        return False
    
    last_call = get_last_random_call()
    hours_since_last = (time.time() - last_call) / 3600
    
    # Need at least 5 hours between calls
    if hours_since_last < 5:
        return False
    
    # Random chance - roughly 1-2 times per day during active hours
    # 10 active hours, want 1-2 calls, so ~10-20% chance per hour check
    # We check less frequently, so adjust probability
    if random.random() < 0.02:  # 2% chance each check cycle
        return True
    
    return False

class RotaryPhone:
    def __init__(self):
        self.pulse_count = 0
        self.last_state = 1
        self.last_change_time = 0
        self.dialed_number = ""
        self.digit_timeout = 0.3
        self.number_timeout = 2.0
        self.offhook_process = None
    
    def is_off_hook(self):
        return GPIO.input(HOOK_PIN) == 1
    
    def is_on_hook(self):
        return GPIO.input(HOOK_PIN) == 0
    
    def wait_for_pickup(self):
        print("Waiting for pickup...")
        while True:
            if self.is_off_hook():
                time.sleep(1.0)
                if self.is_off_hook():
                    print("Handset lifted!")
                    return True
            time.sleep(0.1)
    
    def detect_pulse(self):
        current_state = GPIO.input(ROTARY_PIN)
        now = time.time()
        if self.last_state == 1 and current_state == 0:
            self.pulse_count += 1
            self.last_change_time = now
        self.last_state = current_state
        if self.pulse_count > 0 and (now - self.last_change_time) > self.digit_timeout:
            digit = str(self.pulse_count if self.pulse_count < 10 else 0)
            self.dialed_number += digit
            print(f"Digit dialed: {digit}")
            self.pulse_count = 0
            self.last_change_time = now
            return True
        return False
    
    def play_offhook_tone(self, audio_file):
        try:
            if audio_file and os.path.exists(audio_file):
                self.offhook_process = subprocess.Popen(
                    ["mpg123", "-o", "alsa", "-q", "-a", HANDSET_DEVICE, "--loop", "-1", audio_file],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Playing off-hook audio: {audio_file}")
            else:
                print("Off-hook audio file not found, skipping")
        except Exception as e:
            print(f"Error playing off-hook audio: {e}")
    
    def stop_offhook_tone(self):
        if self.offhook_process:
            try:
                self.offhook_process.terminate()
                self.offhook_process.wait(timeout=1)
                self.offhook_process = None
                print("Stopped off-hook audio")
            except:
                try:
                    self.offhook_process.kill()
                    self.offhook_process = None
                except:
                    pass
    
    def get_dialed_number(self):
        self.dialed_number = ""
        self.pulse_count = 0
        hung_up_start = None
        print("Waiting for number...")
        while True:
            if self.is_on_hook():
                if hung_up_start is None:
                    hung_up_start = time.time()
                elif time.time() - hung_up_start > 0.5:
                    self.stop_offhook_tone()
                    print("Detected stable hang up")
                    return None
            else:
                hung_up_start = None
            self.detect_pulse()
            if self.dialed_number and self.offhook_process:
                self.stop_offhook_tone()
            if self.dialed_number and (time.time() - self.last_change_time) > self.number_timeout:
                number = self.dialed_number
                self.dialed_number = ""
                return number
            time.sleep(0.001)

class VoiceHandler:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
    
    def play_tone(self, frequency=440, duration=0.3):
        try:
            sample_rate = 48000
            num_samples = int(sample_rate * duration)
            beep_file = "/tmp/beep.wav"
            with wave.open(beep_file, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                for i in range(num_samples):
                    fade = 1.0
                    if i < sample_rate * 0.01:
                        fade = i / (sample_rate * 0.01)
                    elif i > num_samples - (sample_rate * 0.01):
                        fade = (num_samples - i) / (sample_rate * 0.01)
                    value = int(32767 * 0.3 * fade * math.sin(2 * math.pi * frequency * i / sample_rate))
                    wav_file.writeframes(struct.pack('<h', value))
            subprocess.run(["aplay", "-D", HANDSET_DEVICE, beep_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(beep_file)
        except Exception as e:
            print(f"[Beep failed: {e}]")
    
    def record_audio(self, filename="recording.wav", max_seconds=10, phone=None):
        print("Recording... Speak now!")
        try:
            cmd = ["arecord", "-D", HANDSET_DEVICE, "-f", "S16_LE", "-r", "48000", "-c", "1", "-d", str(max_seconds), filename]
            if phone:
                process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while process.poll() is None:
                    if phone.is_on_hook():
                        process.terminate()
                        print("Hung up - stopping recording")
                        return None
                    time.sleep(0.05)
            else:
                subprocess.run(cmd, check=True)
            print("Recording complete!")
            self.play_tone(800, 0.3)
            return filename
        except Exception as e:
            print(f"Recording error: {e}")
            return None
    
    def transcribe_audio(self, filename):
        with sr.AudioFile(filename) as source:
            audio = self.recognizer.record(source)
        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return "Sorry, I couldn't understand that."
        except sr.RequestError as e:
            return f"Error with speech recognition: {e}"
    
    def text_to_speech(self, text, output_file="response.wav"):
        cleaned_text = text.replace('*', '').replace('_', '').replace('#', '')
        cleaned_text = cleaned_text.replace('[', '').replace(']', '')
        cleaned_text = cleaned_text.replace('(', '').replace(')', '')
        cleaned_text = cleaned_text.replace('{', '').replace('}', '')
        cleaned_text = cleaned_text.replace('`', '').replace('~', '')
        cleaned_text = ' '.join(cleaned_text.split())
        subprocess.run(["espeak", "-v", "en-us", "-s", "150", "-w", output_file, cleaned_text])
        return output_file
    
    def play_audio(self, filename, check_hangup=False, phone=None, device="handset"):
        print(f"Playing: {filename}")
        audio_device = HANDSET_DEVICE if device == "handset" else INTERNAL_DEVICE
        try:
            subprocess.run(["amixer", "-c", "1" if device == "handset" else "0", "set", "PCM", "100%"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if check_hangup and phone:
                process = subprocess.Popen(["aplay", "-D", audio_device, filename],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while process.poll() is None:
                    if phone.is_on_hook():
                        process.terminate()
                        print("Hung up - stopping audio")
                        return False
                    time.sleep(0.05)
                return True
            else:
                subprocess.run(["aplay", "-D", audio_device, filename], check=True)
                return True
        except Exception as e:
            print(f"Playback error: {e}")
            return True
    
    def play_on_internal(self, filename, phone=None):
        print(f"Playing on internal speaker: {filename}")
        vol = get_internal_volume()
        try:
            subprocess.run(["amixer", "-c", "0", "set", "PCM", "100%"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if filename.lower().endswith(('.mp3', '.mp4')):
                temp_wav = "/tmp/internal_temp.wav"
                temp_loud = "/tmp/internal_loud.wav"
                subprocess.run(["mpg123", "-q", "-w", temp_wav, filename], check=True)
                subprocess.run(["sox", temp_wav, temp_loud, "vol", str(vol)], check=True)
                process = subprocess.Popen(["aplay", "-D", INTERNAL_DEVICE, temp_loud],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while process.poll() is None:
                    if phone and phone.is_off_hook():
                        process.terminate()
                        print("Picked up - stopping internal audio")
                        break
                    time.sleep(0.05)
                try:
                    os.remove(temp_wav)
                    os.remove(temp_loud)
                except:
                    pass
            else:
                temp_loud = "/tmp/internal_loud.wav"
                subprocess.run(["sox", filename, temp_loud, "vol", str(vol)], check=True)
                process = subprocess.Popen(["aplay", "-D", INTERNAL_DEVICE, temp_loud],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                while process.poll() is None:
                    if phone and phone.is_off_hook():
                        process.terminate()
                        print("Picked up - stopping internal audio")
                        break
                    time.sleep(0.05)
                try:
                    os.remove(temp_loud)
                except:
                    pass
        except Exception as e:
            print(f"Internal playback error: {e}")
    
    def cleanup(self):
        self.audio.terminate()

class LLMHandler:
    def __init__(self, api_url, model):
        self.api_url = api_url
        self.model = model
        self.conversation_history = []
        self.system_prompt = """You are an AI assistant on a rotary phone call. Keep these guidelines in mind:
- Keep responses concise and conversational (2-4 sentences typically)
- Speak naturally as if on a phone call
- Avoid using special characters, asterisks, markdown formatting, or symbols
- Don't use lists or bullet points - speak in natural sentences
- If asked how to end the call, tell them to say "goodbye" or "hang up"
- Be helpful, friendly, and to the point"""
    
    def send_message(self, message):
        print(f"Sending to LLM: {message}")
        self.conversation_history.append({"role": "user", "content": message})
        prompt = self._build_prompt()
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            llm_response = result.get("response", "Sorry, I didn't get a response.")
            self.conversation_history.append({"role": "assistant", "content": llm_response})
            print(f"LLM Response: {llm_response}")
            return llm_response
        except Exception as e:
            print(f"Error communicating with LLM: {e}")
            return "Sorry, I'm having trouble connecting right now."
    
    def _build_prompt(self):
        prompt = self.system_prompt + "\n\n"
        for msg in self.conversation_history:
            if msg["role"] == "user":
                prompt += f"User: {msg['content']}\n"
            else:
                prompt += f"Assistant: {msg['content']}\n"
        return prompt
    
    def reset_conversation(self):
        self.conversation_history = []

def find_offhook_audio():
    usb_locations = ["/mnt/usb", "/media/pi", "/media/usb0", "/media/usb"]
    for base_path in usb_locations:
        if os.path.exists(base_path):
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.lower() == "offhook.mp3":
                        full_path = os.path.join(root, file)
                        print(f"Found offhook audio: {full_path}")
                        return full_path
    print("offhook.mp3 not found on USB drive")
    return None

def get_random_simpsons_clip():
    simpsons_folder = "/mnt/usb/Simpsons"
    if not os.path.exists(simpsons_folder):
        simpsons_folder = "/mnt/usb/simpsons"
    if not os.path.exists(simpsons_folder):
        return None
    audio_extensions = ('.mp3', '.wav', '.ogg', '.m4a')
    audio_files = [f for f in os.listdir(simpsons_folder) if f.lower().endswith(audio_extensions)]
    if audio_files:
        return os.path.join(simpsons_folder, random.choice(audio_files))
    return None

def get_dad_joke():
    try:
        response = requests.get("https://icanhazdadjoke.com/", headers={"Accept": "application/json"}, timeout=10)
        if response.status_code == 200:
            return response.json().get("joke", "I couldn't think of a joke.")
        return "Sorry, the joke service is unavailable."
    except:
        return "Sorry, the joke service is unavailable."

def get_random_fact():
    try:
        response = requests.get("https://uselessfacts.jsph.pl/random.json?language=en", timeout=10)
        if response.status_code == 200:
            return response.json().get("text", "I couldn't find a fact.")
        return "Sorry, the facts service is unavailable."
    except:
        return "Sorry, the facts service is unavailable."

def get_this_day_in_history():
    try:
        response = requests.get("http://history.muffinlabs.com/date", timeout=10)
        if response.status_code == 200:
            data = response.json().get("data", {})
            events = data.get("Events", [])
            if events:
                event = random.choice(events)
                year = event.get("year", "Unknown year")
                text = event.get("text", "Something happened.")
                return f"On this day in {year}: {text}"
        return "I couldn't find any historical events for today."
    except:
        return "Sorry, the history service is currently unavailable."

def get_weather(location="Knox, Indiana"):
    try:
        url = f"http://wttr.in/{location.replace(' ', '_').replace(',', '')}?format=%C|%t|%w"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            weather_data = response.text.strip()
            parts = weather_data.split('|')
            if len(parts) >= 3:
                condition = parts[0].strip()
                temp = parts[1].strip().replace('+', '').replace('°F', ' degrees')
                wind = parts[2].strip()
                for arrow in ['↑', '↓', '←', '→', '↖', '↗', '↘', '↙']:
                    wind = wind.replace(arrow, '')
                wind = wind.replace('mph', ' miles per hour')
                return f"The weather in {location} is {condition}, {temp}, with wind at {wind}."
        return f"Sorry, I couldn't retrieve weather for {location}."
    except:
        return "Sorry, the weather service is currently unavailable."

def play_directory(voice, phone):
    directory = """Directory of services:
    Dial 4 1 1 for AI assistant.
    Dial 6 1 1 for music directory.
    Dial 7 4 2 for Simpsons soundboard.
    Dial 7 8 6 for shuffle all music.
    Dial 8 4 6 to set a timer.
    Dial 8 6 5 to set internal speaker volume.
    Dial 5 5 5 1 2 1 2 for weather.
    Dial 5 5 5 3 6 5 3 for a dad joke.
    Dial 5 5 5 3 2 2 8 for a random fact.
    Dial 5 5 5 3 2 8 3 for this day in history.
    Dial 0 to hear this directory again."""
    dir_audio = voice.text_to_speech(directory, "directory.wav")
    voice.play_audio(dir_audio, check_hangup=True, phone=phone)
    os.remove(dir_audio)

def play_music_directory(voice, phone):
    dir_audio = voice.text_to_speech(MUSIC_DIRECTORY, "music_directory.wav")
    voice.play_audio(dir_audio, check_hangup=True, phone=phone)
    os.remove(dir_audio)

def play_ring_and_wait(ring_audio, phone, timeout=20):
    """Play ring audio on internal speaker, return True if picked up"""
    if not ring_audio:
        return False
    
    print("RINGING...")
    vol = get_internal_volume()
    
    # Prepare boosted ring audio
    temp_wav = "/tmp/ring_temp.wav"
    temp_loud = "/tmp/ring_loud.wav"
    
    try:
        subprocess.run(["mpg123", "-q", "-w", temp_wav, ring_audio], check=True)
        subprocess.run(["sox", temp_wav, temp_loud, "vol", str(vol)], check=True)
    except:
        return False
    
    start_time = time.time()
    picked_up = False
    
    while time.time() - start_time < timeout:
        # Play ring once
        process = subprocess.Popen(["aplay", "-D", INTERNAL_DEVICE, temp_loud],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        while process.poll() is None:
            if phone.is_off_hook():
                process.terminate()
                picked_up = True
                break
            time.sleep(0.05)
        
        if picked_up:
            break
        
        # Brief pause between rings
        pause_start = time.time()
        while time.time() - pause_start < 2:
            if phone.is_off_hook():
                picked_up = True
                break
            time.sleep(0.05)
        
        if picked_up:
            break
    
    # Cleanup
    try:
        os.remove(temp_wav)
        os.remove(temp_loud)
    except:
        pass
    
    print("Picked up!" if picked_up else "No answer")
    return picked_up

def handle_incoming_call(phone, voice, llm, ring_audio):
    """Handle a random incoming call"""
    print("\n=== INCOMING CALL ===")
    
    if play_ring_and_wait(ring_audio, phone, timeout=20):
        time.sleep(0.5)
        
        # Pick a random scenario
        scenario = random.choice(CALL_SCENARIOS)
        
        # Set up LLM with the scenario
        llm.conversation_history = []
        llm.system_prompt = f"""You are making a phone call. {scenario}
Keep your responses short and conversational (1-3 sentences).
Stay in character throughout the call.
Don't use special characters or formatting.
If they seem confused or want to end the call, politely say goodbye."""
        
        # LLM starts the conversation
        opener = llm.send_message("You just called and someone picked up. Start the conversation.")
        opener_audio = voice.text_to_speech(opener, "caller_opener.wav")
        voice.play_audio(opener_audio, check_hangup=True, phone=phone)
        os.remove(opener_audio)
        
        # Conversation loop
        turn = 0
        while turn < 10 and phone.is_off_hook():
            turn += 1
            
            audio_file = voice.record_audio(max_seconds=15, phone=phone)
            if not audio_file:
                break
            
            user_msg = voice.transcribe_audio(audio_file)
            print(f"You said: {user_msg}")
            
            if any(kw in user_msg.lower() for kw in ["goodbye", "bye", "hang up", "go away", "stop calling"]):
                bye = llm.send_message(f"They said: {user_msg}. Say a brief goodbye and end the call.")
                bye_audio = voice.text_to_speech(bye, "caller_bye.wav")
                voice.play_audio(bye_audio, check_hangup=True, phone=phone)
                os.remove(bye_audio)
                os.remove(audio_file)
                break
            
            if user_msg and "couldn't understand" not in user_msg:
                resp = llm.send_message(f"They said: {user_msg}")
                resp_audio = voice.text_to_speech(resp, "caller_resp.wav")
                voice.play_audio(resp_audio, check_hangup=True, phone=phone)
                os.remove(resp_audio)
            
            os.remove(audio_file)
        
        # Reset LLM system prompt
        llm.system_prompt = """You are an AI assistant on a rotary phone call. Keep these guidelines in mind:
- Keep responses concise and conversational (2-4 sentences typically)
- Speak naturally as if on a phone call
- Avoid using special characters, asterisks, markdown formatting, or symbols
- Don't use lists or bullet points - speak in natural sentences
- If asked how to end the call, tell them to say "goodbye" or "hang up"
- Be helpful, friendly, and to the point"""
        llm.conversation_history = []
        
        print("=== INCOMING CALL ENDED ===\n")
        return True
    
    return False

def handle_timer_ring(phone, voice, ring_audio):
    """Handle timer going off"""
    print("\n=== TIMER ALARM ===")
    
    if play_ring_and_wait(ring_audio, phone, timeout=30):
        time.sleep(0.5)
        msg = voice.text_to_speech("Your timer is complete!", "timer_done.wav")
        voice.play_audio(msg, check_hangup=True, phone=phone)
        os.remove(msg)
        print("=== TIMER ACKNOWLEDGED ===\n")
    else:
        print("=== TIMER MISSED ===\n")
    
    clear_timer()

def play_farewell(voice, phone):
    farewells = ["Thank you for calling. Goodbye!", "Thanks for calling!", "Goodbye, and have a great day!", "Thank you, goodbye!"]
    farewell = random.choice(farewells)
    farewell_audio = voice.text_to_speech(farewell, "farewell.wav")
    voice.play_audio(farewell_audio, check_hangup=True, phone=phone)
    os.remove(farewell_audio)

def play_music_session(files, voice, phone):
    if not files:
        err = voice.text_to_speech("Sorry, no music files found.", "music_err.wav")
        voice.play_audio(err, check_hangup=True, phone=phone)
        os.remove(err)
        return
    
    random.shuffle(files)
    file_index = 0
    playing_internal = False
    vol = get_internal_volume()
    
    intro = voice.text_to_speech(f"Playing {len(files)} songs on shuffle.", "music_intro.wav")
    voice.play_audio(intro, check_hangup=True, phone=phone)
    os.remove(intro)
    
    while file_index < len(files):
        current_file = files[file_index]
        print(f"Now playing ({file_index + 1}/{len(files)}): {os.path.basename(current_file)}")
        
        if phone.is_off_hook() and not playing_internal:
            if current_file.lower().endswith(('.mp3', '.mp4')):
                process = subprocess.Popen(["mpg123", "-o", "alsa", "-q", "-a", HANDSET_DEVICE, current_file],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process = subprocess.Popen(["aplay", "-D", HANDSET_DEVICE, current_file],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            while process.poll() is None:
                if phone.is_on_hook():
                    process.terminate()
                    print("Hung up - transferring to internal speaker")
                    playing_internal = True
                    break
                time.sleep(0.05)
            
            if not playing_internal:
                file_index += 1
                continue
        
        if playing_internal or phone.is_on_hook():
            playing_internal = True
            temp_wav = "/tmp/music_temp.wav"
            temp_loud = "/tmp/music_loud.wav"
            
            try:
                if current_file.lower().endswith(('.mp3', '.mp4')):
                    subprocess.run(["mpg123", "-q", "-w", temp_wav, current_file], check=True)
                else:
                    temp_wav = current_file
                
                subprocess.run(["sox", temp_wav, temp_loud, "vol", str(vol)], check=True)
                
                process = subprocess.Popen(["aplay", "-D", INTERNAL_DEVICE, temp_loud],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                while process.poll() is None:
                    if phone.is_off_hook():
                        process.terminate()
                        print("Picked up - stopping music")
                        try:
                            if temp_wav != current_file:
                                os.remove(temp_wav)
                            os.remove(temp_loud)
                        except:
                            pass
                        return
                    time.sleep(0.05)
                
                try:
                    if temp_wav != current_file:
                        os.remove(temp_wav)
                    os.remove(temp_loud)
                except:
                    pass
                    
            except Exception as e:
                print(f"Music playback error: {e}")
            
            file_index += 1
    
    print("Playlist finished")

def main():
    phone = RotaryPhone()
    voice = VoiceHandler()
    llm = LLMHandler(LLM_API_URL, LLM_MODEL)
    offhook_audio = find_offhook_audio()
    ring_audio = find_ring_audio()
    
    print("Rotary Phone LLM Interface Ready!")
    print("Dial 0 for directory")
    print("Dial 411 for AI assistant")
    print("Dial 611 for music directory")
    print("Dial 742 for Simpsons soundboard")
    print("Dial 786 for shuffle all music")
    print("Dial 182 for Blink-182")
    print("Dial 7861-7867 for specific albums")
    print("Dial 865 for volume control")
    print("Dial 555-1212 for weather")
    print("Dial 555-JOKE (5553653) for dad jokes")
    print("Dial 555-FACT (5553228) for random facts")
    print("Dial 555-DATE (5553283) for this day in history")
    
    time.sleep(3)
    phone.pulse_count = 0
    phone.dialed_number = ""
    phone.last_state = GPIO.input(ROTARY_PIN)
    
    try:
        while True:
            print("\n--- Phone idle. Waiting for pickup... ---")
            phone.wait_for_pickup()
            
            phone.pulse_count = 0
            phone.dialed_number = ""
            time.sleep(0.5)
            
            while phone.is_off_hook():
                if offhook_audio and not phone.offhook_process:
                    phone.play_offhook_tone(offhook_audio)
                
                number = phone.get_dialed_number()
                
                if number is None:
                    print("Hung up - returning to idle")
                    phone.stop_offhook_tone()
                    time.sleep(1.0)
                    break
                
                if not number:
                    continue
                
                print(f"\nNumber dialed: {number}")
                handled = False
                
                if number == "0":
                    play_directory(voice, phone)
                    handled = True
                
                elif number == "611":
                    play_music_directory(voice, phone)
                    handled = True
                
                elif number == "742":
                    print("\n=== SIMPSONS SOUNDBOARD ===")
                    clip = get_random_simpsons_clip()
                    if clip:
                        if clip.lower().endswith('.mp3'):
                            process = subprocess.Popen(["mpg123", "-o", "alsa", "-q", "-a", HANDSET_DEVICE, clip],
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            while process.poll() is None:
                                if phone.is_on_hook():
                                    process.terminate()
                                    print("Hung up - transferring to internal speaker")
                                    voice.play_on_internal(clip, phone)
                                    break
                                time.sleep(0.05)
                        else:
                            if not voice.play_audio(clip, check_hangup=True, phone=phone):
                                voice.play_on_internal(clip, phone)
                    else:
                        err = voice.text_to_speech("Sorry, no Simpsons clips found.", "err.wav")
                        voice.play_audio(err, check_hangup=True, phone=phone)
                        os.remove(err)
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "5551212":
                    print("\n=== WEATHER SERVICE ===")
                    intro = voice.text_to_speech("Checking the current weather for Knox, Indiana.", "w1.wav")
                    voice.play_audio(intro, check_hangup=True, phone=phone)
                    os.remove(intro)
                    if phone.is_off_hook():
                        weather = voice.text_to_speech(get_weather(), "w2.wav")
                        voice.play_audio(weather, check_hangup=True, phone=phone)
                        os.remove(weather)
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "5553653":
                    print("\n=== JOKE HOTLINE ===")
                    intro = voice.text_to_speech("Here's a dad joke for you.", "j1.wav")
                    voice.play_audio(intro, check_hangup=True, phone=phone)
                    os.remove(intro)
                    if phone.is_off_hook():
                        joke = voice.text_to_speech(get_dad_joke(), "j2.wav")
                        voice.play_audio(joke, check_hangup=True, phone=phone)
                        os.remove(joke)
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "5553228":
                    print("\n=== FACTS LINE ===")
                    intro = voice.text_to_speech("Here's a random fact for you.", "f1.wav")
                    voice.play_audio(intro, check_hangup=True, phone=phone)
                    os.remove(intro)
                    if phone.is_off_hook():
                        fact = voice.text_to_speech(get_random_fact(), "f2.wav")
                        voice.play_audio(fact, check_hangup=True, phone=phone)
                        os.remove(fact)
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "5553283":
                    print("\n=== HISTORY LINE ===")
                    intro = voice.text_to_speech("Here's what happened on this day in history.", "h1.wav")
                    voice.play_audio(intro, check_hangup=True, phone=phone)
                    os.remove(intro)
                    if phone.is_off_hook():
                        history = voice.text_to_speech(get_this_day_in_history(), "h2.wav")
                        voice.play_audio(history, check_hangup=True, phone=phone)
                        os.remove(history)
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "865":
                    print("\n=== VOLUME CONTROL ===")
                    current = get_internal_volume()
                    prompt = f"Internal speaker volume. Currently set to {current}x. Dial 1 for normal, 2 for double, 3 for triple."
                    prompt_audio = voice.text_to_speech(prompt, "vol_prompt.wav")
                    voice.play_audio(prompt_audio, check_hangup=True, phone=phone)
                    os.remove(prompt_audio)
                    
                    if phone.is_off_hook():
                        phone.dialed_number = ""
                        phone.pulse_count = 0
                        start_time = time.time()
                        vol_digit = None
                        
                        while time.time() - start_time < 10 and phone.is_off_hook():
                            phone.detect_pulse()
                            if phone.dialed_number:
                                vol_digit = phone.dialed_number
                                phone.dialed_number = ""
                                break
                            time.sleep(0.01)
                        
                        if vol_digit in ["1", "2", "3"]:
                            vol_map = {"1": 1.0, "2": 2.0, "3": 3.0}
                            set_internal_volume(vol_map[vol_digit])
                            confirm = f"Volume set to {vol_digit}x."
                            confirm_audio = voice.text_to_speech(confirm, "vol_confirm.wav")
                            voice.play_audio(confirm_audio, check_hangup=True, phone=phone)
                            os.remove(confirm_audio)
                        else:
                            err = voice.text_to_speech("No valid selection. Volume unchanged.", "vol_err.wav")
                            voice.play_audio(err, check_hangup=True, phone=phone)
                            os.remove(err)
                    
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number == "846":
                    print("\n=== TIMER ===")
                    prompt = "Set a timer. Dial the number of minutes, then wait."
                    prompt_audio = voice.text_to_speech(prompt, "timer_prompt.wav")
                    voice.play_audio(prompt_audio, check_hangup=True, phone=phone)
                    os.remove(prompt_audio)
                    
                    if phone.is_off_hook():
                        phone.dialed_number = ""
                        phone.pulse_count = 0
                        start_time = time.time()
                        
                        # Wait for digits (up to 10 seconds of inactivity)
                        while time.time() - start_time < 10 and phone.is_off_hook():
                            phone.detect_pulse()
                            if phone.dialed_number:
                                start_time = time.time()  # Reset timeout when digit received
                            if phone.dialed_number and (time.time() - phone.last_change_time) > 2:
                                break
                            time.sleep(0.01)
                        
                        if phone.dialed_number:
                            try:
                                minutes = int(phone.dialed_number)
                                if 1 <= minutes <= 99:
                                    set_timer(minutes)
                                    confirm = f"Timer set for {minutes} minute{'s' if minutes > 1 else ''}."
                                    confirm_audio = voice.text_to_speech(confirm, "timer_confirm.wav")
                                    voice.play_audio(confirm_audio, check_hangup=True, phone=phone)
                                    os.remove(confirm_audio)
                                else:
                                    err = voice.text_to_speech("Please enter a number between 1 and 99.", "timer_err.wav")
                                    voice.play_audio(err, check_hangup=True, phone=phone)
                                    os.remove(err)
                            except:
                                err = voice.text_to_speech("Invalid number. Timer not set.", "timer_err.wav")
                                voice.play_audio(err, check_hangup=True, phone=phone)
                                os.remove(err)
                        else:
                            err = voice.text_to_speech("No number entered. Timer not set.", "timer_err.wav")
                            voice.play_audio(err, check_hangup=True, phone=phone)
                            os.remove(err)
                        
                        phone.dialed_number = ""
                    
                    if phone.is_off_hook():
                        play_farewell(voice, phone)
                    handled = True
                
                elif number in MUSIC_FOLDERS:
                    print(f"\n=== MUSIC: {number} ===")
                    files = get_music_files(number)
                    play_music_session(files, voice, phone)
                    handled = True
                
                elif number == "411":
                    print("\n=== CALL CONNECTED ===")
                    llm.reset_conversation()
                    
                    inst = voice.text_to_speech("You have 15 seconds to speak. A beep signals when time is up.", "inst.wav")
                    voice.play_audio(inst, check_hangup=True, phone=phone)
                    os.remove(inst)
                    
                    if phone.is_off_hook():
                        time.sleep(0.5)
                        greet = voice.text_to_speech("Hello! I'm your AI assistant. How can I help?", "greet.wav")
                        voice.play_audio(greet, check_hangup=True, phone=phone)
                        os.remove(greet)
                    
                    turn = 0
                    while turn < 20 and phone.is_off_hook():
                        turn += 1
                        audio_file = voice.record_audio(max_seconds=15, phone=phone)
                        if not audio_file:
                            break
                        
                        user_msg = voice.transcribe_audio(audio_file)
                        print(f"You said: {user_msg}")
                        
                        if any(kw in user_msg.lower() for kw in ["goodbye", "bye", "hang up", "end call"]):
                            bye = voice.text_to_speech("Goodbye! Call again anytime.", "bye.wav")
                            voice.play_audio(bye, check_hangup=True, phone=phone)
                            os.remove(bye)
                            os.remove(audio_file)
                            break
                        
                        if user_msg and "couldn't understand" not in user_msg:
                            resp = llm.send_message(user_msg)
                            resp_audio = voice.text_to_speech(resp)
                            voice.play_audio(resp_audio, check_hangup=True, phone=phone)
                            os.remove(resp_audio)
                        else:
                            retry = voice.text_to_speech("Sorry, I didn't catch that. Could you repeat?", "retry.wav")
                            voice.play_audio(retry, check_hangup=True, phone=phone)
                            os.remove(retry)
                        os.remove(audio_file)
                    
                    voice.play_tone(600, 0.5)
                    handled = True
                
                if not handled:
                    print(f"Number {number} is not configured.")
                    err_msg = f"The number you dialed, {' '.join(str(number))}, is not in service. Dial 0 for a directory."
                    err = voice.text_to_speech(err_msg, "error.wav")
                    voice.play_audio(err, check_hangup=True, phone=phone)
                    os.remove(err)
                
                time.sleep(0.3)
                if phone.is_on_hook():
                    time.sleep(0.5)
                    if phone.is_on_hook():
                        print("Hung up after service")
                        phone.stop_offhook_tone()
                        break
            
            phone.stop_offhook_tone()
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        phone.stop_offhook_tone()
    finally:
        phone.stop_offhook_tone()
        voice.cleanup()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
