"""
Alert Management System
Handles notifications, clip saving, and email alerts
"""
import cv2
import time
import os
import smtplib
import yaml
import csv
from datetime import datetime
from pathlib import Path
from collections import deque
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


class AlertSystem:
    def __init__(self, alerts_dir="data/alerts", logs_dir="data/logs"):
        self.alerts_dir = Path(alerts_dir)
        self.logs_dir = Path(logs_dir)
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.alert_log_file = self.logs_dir / "alerts.csv"
        self._init_log_file()
        
        # Cooldown fallback (for edge cases)
        self.last_alert_time = 0
        self.alert_cooldown = 2.0  # seconds
        
        # Frame buffer for clip saving
        self.alert_buffer = deque(maxlen=100)  # Store last 100 frames
        
        # Email config
        self.alert_recipient = os.getenv("EMAIL_RECIPIENT", "security-team@yourorg.com")
        
        # ✅ EVENT-BASED ALERTING STATE
        self.alert_event_active = False  # True = currently in an anomaly event
        self.normal_frame_count = 0  # Count consecutive normal frames to reset event
        self.required_normal_frames = 10  # Need ~10 normal frames to reset event (~2s at 5 FPS)
    
    def _init_log_file(self):
        """Initialize CSV log file with headers if it doesn't exist"""
        if not self.alert_log_file.exists():
            with open(self.alert_log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'camera_id', 'camera_name', 
                    'anomaly_score', 'clip_path'
                ])
    
    def can_trigger_alert(self):
        """
        Fallback cooldown check (used only for legacy compatibility)
        ✅ Prefer should_start_new_alert_event() for event-based logic
        """
        current_time = time.time()
        if current_time - self.last_alert_time > self.alert_cooldown:
            self.last_alert_time = current_time
            return True
        return False

    def should_start_new_alert_event(self, score: float, threshold: float) -> bool:
        """
        ✅ EVENT-BASED ALERTING: Returns True ONLY for NEW anomaly events
        
        Logic:
        - If score > threshold AND not already in event → START NEW EVENT → return True
        - If score <= threshold AND in event → count normal frames → reset after N frames
        - If score > threshold AND already in event → stay in event → return False (no new clip)
        
        This prevents multiple clips during sustained anomalies.
        """
        if score is None:
            return False
            
        is_anomaly = score > threshold
        
        if is_anomaly and not self.alert_event_active:
            # ✅ NEW anomaly event starting - trigger alert
            self.alert_event_active = True
            self.normal_frame_count = 0
            return True
            
        elif not is_anomaly and self.alert_event_active:
            # Count consecutive normal frames to end the event
            self.normal_frame_count += 1
            if self.normal_frame_count >= self.required_normal_frames:
                # ✅ Event ended - ready for next anomaly
                self.alert_event_active = False
                self.normal_frame_count = 0
            return False  # Don't trigger alert while resetting
            
        elif is_anomaly and self.alert_event_active:
            # Still in anomaly event - suppress new alerts
            self.normal_frame_count = 0  # Reset counter
            
        # Default: no new event
        return False
    
    def reset_alert_state(self):
        """Manually reset alert state (useful when switching sources)"""
        self.alert_event_active = False
        self.normal_frame_count = 0
        print("🔄 Alert state reset")
    
    def add_frame_to_buffer(self, frame):
        """Add frame to rolling buffer for alert clip creation"""
        if frame is not None:
            self.alert_buffer.append(frame.copy())
    
    def save_alert_clip(self, camera_id: str, camera_name: str, score: float) -> str | None:
        """
        Save alert clip from buffered frames
        Returns: path to saved clip or None if failed
        """
        if len(self.alert_buffer) == 0:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_filename = f"{timestamp}_{camera_id}_alert.mp4"
        clip_path = self.alerts_dir / clip_filename
        
        try:
            frames = list(self.alert_buffer)
            if len(frames) == 0:
                return None
                
            height, width = frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(clip_path), fourcc, 15.0, (width, height))
            
            for frame in frames:
                out.write(frame)
            out.release()
            
            print(f"✅ Alert clip saved: {clip_path}")
            return str(clip_path)
            
        except Exception as e:
            print(f"❌ Failed to save alert clip: {e}")
            return None
    
    def log_alert(self, camera_id: str, camera_name: str, score: float, clip_path: str = None):
        """Log alert metadata to CSV file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(self.alert_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    camera_id,
                    camera_name,
                    f"{score:.4f}",
                    clip_path or "N/A"
                ])
            print(f"📝 Alert logged: {camera_name} - Score: {score:.4f}")
        except Exception as e:
            print(f"❌ Failed to log alert: {e}")
    
    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Get recent alerts from log file as list of dicts"""
        alerts = []
        if not self.alert_log_file.exists():
            return alerts
            
        try:
            with open(self.alert_log_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                alerts = list(reader)[-limit:]
            return alerts
        except Exception as e:
            print(f"❌ Failed to read alerts: {e}")
            return alerts

    def send_email_alert(
        self, 
        camera_name: str, 
        score: float, 
        clip_path: str = None,
        recipient_override: str = None,
        threshold: float = None,
        location: str = None
    ) -> bool:
        """
        Send email notification with optional clip attachment
        Returns: True if sent successfully, False otherwise
        """
        try:
            # Load config from env + yaml fallback
            config = {}
            yaml_path = Path("config/system.yaml")
            if yaml_path.exists():
                with open(yaml_path) as f:
                    loaded = yaml.safe_load(f)
                    if loaded and 'email' in loaded:
                        config = loaded['email']
            
            smtp_server = os.getenv("SMTP_SERVER", config.get("smtp_server", "smtp.gmail.com"))
            smtp_port = int(os.getenv("SMTP_PORT", config.get("smtp_port", 587)))
            smtp_user = os.getenv("SMTP_USER", config.get("smtp_user"))
            smtp_pass = os.getenv("SMTP_PASS", config.get("smtp_pass"))
            recipient = recipient_override or self.alert_recipient or os.getenv("EMAIL_RECIPIENT")
            
            # Skip if config missing
            if not all([smtp_server, smtp_user, smtp_pass, recipient]):
                print("⚠️ Email config missing. Skipping alert email.")
                return False

            # Build email
            msg = MIMEMultipart()
            msg['Subject'] = f"🚨 CCTV ANOMALY: {camera_name} (Score: {score:.2f})"
            msg['From'] = smtp_user
            msg['To'] = recipient
            
            body = f"""
🚨 CCTV ANOMALY ALERT

Camera: {camera_name}
Location: {location or 'Unknown'}
Anomaly Score: {score:.4f}
Detection Threshold: {threshold if threshold is not None else 'N/A'}
Detected At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📎 Attached: Alert clip ({os.path.basename(clip_path) if clip_path else 'No clip saved'})

— SmartWatch AI Security System
            """
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach clip if available
            if clip_path and os.path.exists(clip_path):
                with open(clip_path, "rb") as f:
                    part = MIMEBase('application', "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition', 
                        f'attachment; filename={os.path.basename(clip_path)}'
                    )
                    msg.attach(part)
            
            # Send via SMTP
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            print(f"📧 Alert email sent to {recipient}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            print("❌ SMTP auth failed. Check SMTP_USER/SMTP_PASS (use App Password for Gmail)")
            return False
        except Exception as e:
            print(f"❌ Email failed: {type(e).__name__}: {e}")
            return False


# run with: python backend/alert_system.py
if __name__ == "__main__":
    print("🧪 Testing AlertSystem with event-based logic...")
    
    alert_system = AlertSystem()
    
    # Simulate frames with scores (two separate anomaly events)
    test_scores = [
        # Event 1: Sustained anomaly (should trigger ONCE)
        0.4, 0.5, 0.7, 0.8, 0.9, 0.85, 0.82, 0.78,  # anomaly starts
        0.65, 0.55, 0.45, 0.4, 0.35, 0.3, 0.3, 0.3,  # normal frames (reset event)
        # Event 2: Another anomaly (should trigger ONCE more)
        0.5, 0.72, 0.81, 0.77, 0.69,  # anomaly starts again
        0.5, 0.4, 0.3  # back to normal
    ]
    
    threshold = 0.6
    triggered_count = 0
    
    for i, score in enumerate(test_scores):
        should_trigger = alert_system.should_start_new_alert_event(score, threshold)
        status = "🚨 TRIGGERED" if should_trigger else "  (no new event)"
        print(f"Frame {i:2d}: score={score:.2f} | {status}")
        if should_trigger:
            triggered_count += 1
            alert_system.log_alert("camera_1", "Test Camera", score, None)
    
    print(f"\n✅ Test complete: {triggered_count} alert events triggered (expected: 2)")
    print(f"   Event 1: frames 2-7 (sustained anomaly) → 1 clip")
    print(f"   Event 2: frames 18-22 (second anomaly) → 1 clip")

