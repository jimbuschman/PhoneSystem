# Rotary Phone LLM Interface - Installation Guide

## Hardware Overview

- Raspberry Pi Zero (with GPIO header)
- Rotary phone with connections to GPIO pins:
  - **Rotary dial pulse pin**: GPIO 17
  - **Hook switch pin**: GPIO 27
- USB hub with:
  - Two generic USB audio dongles (plug and play, no special drivers)
  - USB drive for music/audio files
- Audio devices:
  - **Handset audio**: `plughw:1,0` (one USB dongle)
  - **Internal speaker**: `plughw:0,0` (other USB dongle)
- USB drive mounted at `/mnt/usb`

## 1. Fresh Raspberry Pi OS Setup

Flash Raspberry Pi OS Lite (or Desktop) to SD card. Enable SSH and configure WiFi during imaging (using Raspberry Pi Imager).

Boot the Pi and SSH in:
```bash
ssh pi@raspberrypi.local
```

Update the system:
```bash
sudo apt update && sudo apt upgrade -y
```

## 2. Install System Dependencies

```bash
sudo apt install -y \
    python3-full \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    espeak \
    mpg123 \
    sox \
    alsa-utils \
    libportaudio2 \
    portaudio19-dev \
    flac
```

## 3. Create Project Directory

```bash
mkdir -p /home/pi/rotary-phone
cd /home/pi/rotary-phone
```

## 4. Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Install Python packages:
```bash
pip install --upgrade pip
pip install \
    RPi.GPIO \
    pyaudio \
    SpeechRecognition \
    requests \
    webrtcvad \
    setuptools
```

## 5. Copy the Main Script

Copy `rotary_phone_vad.py` to `/home/pi/rotary-phone/`

(The full script is saved separately - get it from backup or this chat)

## 6. Mount USB Drive

Create mount point:
```bash
sudo mkdir -p /mnt/usb
```

Find your USB drive:
```bash
lsblk
```

Add to `/etc/fstab` for auto-mount (adjust device if needed):
```bash
sudo nano /etc/fstab
```

Add this line (assuming USB is /dev/sda1):
```
/dev/sda1 /mnt/usb auto defaults,nofail,x-systemd.automount 0 0
```

Mount it:
```bash
sudo mount -a
```

## 7. USB Drive Contents

The USB drive should have:
```
/mnt/usb/
├── offhook.mp3          # Dial tone sound (plays when phone lifted)
├── ring.mp3             # Ring sound for incoming calls/timer
├── Simpsons/            # Simpsons audio clips (for 742 soundboard)
│   ├── clip1.mp3
│   └── ...
└── Music/               # Music library
    ├── Blink-182 Neighborhoods (Deluxe) (Full Album)/
    ├── blink182/
    ├── Motion City Soundtrack - My Dinosaur Life/
    ├── Taking Back Sunday - Tell All Your Friends/
    ├── When Broken Is Easily Fixed - Silverstein/
    ├── Where You Want To Be/
    ├── Yarn/
    └── TomPetty/
        ├── Finding Wildflowers/
        └── Wildflowers and all the Rest/
```

## 8. Create Systemd Service

```bash
sudo nano /etc/systemd/system/rotary-phone.service
```

Paste:
```ini
[Unit]
Description=Rotary Phone LLM Interface
After=network.target sound.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/rotary-phone
ExecStartPre=/bin/sleep 5
ExecStart=/home/pi/rotary-phone/venv/bin/python /home/pi/rotary-phone/rotary_phone_vad.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rotary-phone
sudo systemctl start rotary-phone
```

## 9. LLM Server (Ollama)

The phone connects to a local LLM server running on your main PC at:
```
http://192.168.0.49:11434/api/generate
```

This runs **Ollama** with the **gemma3** model.

On your main PC, install Ollama:
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3
```

Make sure Ollama is listening on all interfaces (not just localhost). You may need to set:
```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

**Note:** The IP `192.168.0.49` is your main PC's local IP. If it changes, update `LLM_API_URL` in the script.

## 10. Audio Device Configuration

Check your audio devices:
```bash
aplay -l
arecord -l
```

The script expects:
- **Card 1** (`plughw:1,0`): Handset USB audio (speaker + mic)
- **Card 0** (`plughw:0,0`): Internal speaker

If your devices are different, update these lines in the script:
```python
HANDSET_DEVICE = "plughw:1,0"
INTERNAL_DEVICE = "plughw:0,0"
```

Test audio:
```bash
# Test playback to handset
aplay -D plughw:1,0 /path/to/test.wav

# Test recording from handset
arecord -D plughw:1,0 -f S16_LE -r 48000 -c 1 -d 5 test.wav
```

## 11. GPIO Wiring

| Function | GPIO Pin | Notes |
|----------|----------|-------|
| Rotary dial pulses | GPIO 17 | Pull-up enabled |
| Hook switch | GPIO 27 | Pull-up enabled; HIGH = off-hook |

Both use internal pull-up resistors (configured in code).

## 12. Verify Installation

Check service status:
```bash
sudo systemctl status rotary-phone
```

View logs:
```bash
sudo journalctl -u rotary-phone -f
```

## 13. Phone Directory

| Dial | Service |
|------|---------|
| 0 | Directory |
| 411 | AI Assistant |
| 611 | Music Directory |
| 742 | Simpsons Soundboard |
| 786 | Shuffle All Music |
| 182 | Blink-182 |
| 7861-7867 | Specific Albums |
| 846 | Set Timer |
| 865 | Volume Control |
| 555-1212 | Weather (Knox, Indiana) |
| 555-3653 | Dad Jokes |
| 555-3228 | Random Facts |
| 555-3283 | This Day in History |

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u rotary-phone -n 50
```

### Test script manually
```bash
cd /home/pi/rotary-phone
sudo /home/pi/rotary-phone/venv/bin/python rotary_phone_vad.py
```

### Module not found errors
Make sure you're installing in the venv:
```bash
/home/pi/rotary-phone/venv/bin/pip install <module>
```

### Audio issues
- Check `alsamixer` for volume levels
- Verify device names with `aplay -l` and `arecord -l`
- Test devices directly with `aplay` and `arecord`

### VAD not detecting speech
- Adjust `silence_timeout` (default 1.5s)
- Adjust VAD aggressiveness: `webrtcvad.Vad(2)` - try 1 or 3
- Check mic input levels

## Files Created by the Script

These are created at runtime:
- `/home/pi/rotary-phone/volume_setting.txt` - Internal speaker volume (1.0-3.0)
- `/home/pi/rotary-phone/timer.txt` - Active timer end time
- `/home/pi/rotary-phone/last_random_call.txt` - Last incoming call timestamp
