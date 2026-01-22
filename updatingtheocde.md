sudo systemctl stop rotary-phone.service
nano ~/rotary-phone/rotary_llm.py
Delete all, paste updated code, save, then:
sudo systemctl restart rotary-phone.service


# View live logs
sudo journalctl -u rotary-phone.service -f

# Stop the service
sudo systemctl stop rotary-phone.service

# Restart after code changes
sudo systemctl restart rotary-phone.service

# Disable auto-start
sudo systemctl disable rotary-phone.service
