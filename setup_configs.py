# setup_configs.py - Run this BEFORE app.py
import os
import json
import yaml

# Create config directory
os.makedirs("config", exist_ok=True)

# Create cameras.json
cameras_config = {
    "cameras": [
        {
            "id": "camera_1",
            "name": "Webcam",
            "rtsp_url": "0",  # Use webcam (change to RTSP URL later)
            "location": "Office",
            "enabled": True
        }
    ]
}
with open("config/cameras.json", "w") as f:
    json.dump(cameras_config, f, indent=2)

# Create system.yaml
system_config = {
    "inference": {
        "device": "cpu",  # Start with CPU (change to "cuda" later if GPU available)
        "window_size": 30,
        "threshold": 0.6,
        "fps": 15
    },
    "alerts": {
        "cooldown_seconds": 2.0,
        "save_clips": True,
        "clip_duration_seconds": 10
    },
    "dashboard": {
        "refresh_rate_ms": 200,
        "max_alerts_display": 50
    }
}
with open("config/system.yaml", "w") as f:
    yaml.dump(system_config, f)

print("✅ Config files created successfully!")
print("   - config/cameras.json")
print("   - config/system.yaml")
print("\n👉 Now run: python app.py")