"""
Main FastAPI Application - CCTV Anomaly Detection Dashboard
"""
from fastapi import FastAPI, Request, WebSocket, UploadFile, File, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

import base64
import cv2
import uvicorn
import asyncio
import threading
import time
import os
import json
from datetime import datetime
from collections import deque
from pathlib import Path
from dotenv import load_dotenv
import numpy as np

# Import backend modules
from backend.inference_engine import InferenceEngine
from backend.camera_manager import CameraManager
from backend.alert_system import AlertSystem

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="CCTV Anomaly Detection Dashboard")

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# Global instances
camera_manager = None
inference_engine = None
alert_system = None
motion_filter = None

# SOURCE MANAGER: Ensure only ONE source active at a time (camera OR upload)

class SourceManager:
    def __init__(self):
        self.active_source = None  # "camera" or "upload"
        self.upload_cap = None
        self.upload_thread = None
        self.lock = threading.Lock()
    
    def switch_to_camera(self):
        """Stop upload processing and switch to camera"""
        with self.lock:
            if self.active_source == "upload" and self.upload_cap:
                self.upload_cap.release()
                self.upload_cap = None
                print("📹 Stopped upload processing, switching to camera")
            self.active_source = "camera"
    
    def switch_to_upload(self, video_path: str):
        """Stop camera and switch to upload processing"""
        with self.lock:
            if self.active_source == "camera":
                if camera_manager:
                    camera_manager.stop_all()
                print("📹 Stopped camera, switching to upload")
            self.active_source = "upload"
            self.upload_cap = cv2.VideoCapture(video_path)
            return self.upload_cap.isOpened()
    
    def stop_all(self):
        """Stop all sources"""
        with self.lock:
            if self.upload_cap:
                self.upload_cap.release()
                self.upload_cap = None
            if camera_manager and self.active_source == "camera":
                camera_manager.stop_all()
            self.active_source = None

source_manager = SourceManager()

# Score history for graph (last 60 entries ~1 min at 1 FPS)
score_history = deque(maxlen=60)
upload_score_history = deque(maxlen=60)

# CAMERA MOTION FILTER: Suppress false alerts from camera panning/shaking

class CameraMotionFilter:
    def __init__(self, threshold=0.25, min_features=20):
        self.prev_gray = None
        self.threshold = threshold
        self.min_features = min_features
    
    def is_camera_motion(self, frame):
        if frame is None:
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None:
            self.prev_gray = gray
            return False
        prev_pts = cv2.goodFeaturesToTrack(
            self.prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=10
        )
        if prev_pts is None or len(prev_pts) < self.min_features:
            self.prev_gray = gray
            return False
        curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, gray, prev_pts, None
        )
        valid = status.ravel() == 1
        if valid.sum() < self.min_features:
            self.prev_gray = gray
            return False
        motion_vecs = curr_pts[valid] - prev_pts[valid]
        avg_motion = np.mean(np.linalg.norm(motion_vecs, axis=1))
        self.prev_gray = gray
        return avg_motion > self.threshold

# STARTUP / SHUTDOWN EVENTS

@app.on_event("startup")
async def startup_event():
    global camera_manager, inference_engine, alert_system, motion_filter
    print("🚀 Starting CCTV Anomaly Detection System...")
    
    camera_manager = CameraManager()
    # Don't auto-start - wait for user command
    
    model_path = os.getenv("MODEL_PATH", "backend/models/best_lstm_multidataset.pt")
    inference_engine = InferenceEngine(model_path=model_path)
    
    alert_system = AlertSystem()
    motion_filter = CameraMotionFilter(threshold=0.25)
    
    print("✅ System initialized successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    source_manager.stop_all()
    print("⏹️ System shutdown complete")

# API ENDPOINTS

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def get_status():
    return {
        "status": "running",
        "active_source": source_manager.active_source,
        "cameras": camera_manager.get_status() if camera_manager else {},
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/alerts")
async def get_alerts(limit: int = 50):
    if alert_system:
        return {"alerts": alert_system.get_recent_alerts(limit)}
    return {"alerts": []}

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Handle video file upload and process frame-by-frame"""
    upload_path = Path("data/uploads") / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded file
    with open(upload_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Switch to upload source (automatically stops camera)
    if not source_manager.switch_to_upload(str(upload_path)):
        return {"status": "error", "message": "Failed to open video file"}
    
    # Process video in background thread
    def process_uploaded_video(path: str):
        cap = source_manager.upload_cap
        frame_count = 0
        while cap.isOpened() and source_manager.active_source == "upload":
            ret, frame = cap.read()
            if not ret:
                break
            
            alert_system.add_frame_to_buffer(frame)
            score, is_alert = inference_engine.predict(frame)
            
            if score is not None:
                upload_score_history.append({
                    "time": datetime.now().strftime("%H:%M:%S"), 
                    "score": float(score)
                })
            
            # ✅ EVENT-BASED ALERTING: One clip per anomaly event
            if score is not None and alert_system.should_start_new_alert_event(
                score, inference_engine.threshold
            ):
                clip_path = alert_system.save_alert_clip("upload", "Uploaded Video", score)
                alert_system.log_alert("upload", "Uploaded Video", score, clip_path)
                alert_system.send_email_alert(
                    camera_name="Uploaded Video",
                    score=score,
                    clip_path=clip_path,
                    threshold=inference_engine.threshold,
                    location="Upload Source"
                )
            
            frame_count += 1
            time.sleep(0.03)  # Prevent CPU overload
        
        cap.release()
        source_manager.upload_cap = None
        print(f"✅ Processed {frame_count} frames from {path}")
    
    source_manager.upload_thread = threading.Thread(
        target=process_uploaded_video, 
        args=(str(upload_path),), 
        daemon=True
    )
    source_manager.upload_thread.start()
    
    return {
        "status": "processing",
        "filename": file.filename,
        "message": "Video uploaded. Processing in background. Watch the dashboard."
    }

@app.post("/api/camera/start")
async def start_camera(camera_type: str = "0", rtsp_url: str = ""):
    """Start camera stream (stops upload if running)"""
    source_manager.switch_to_camera()
    
    # Update RTSP URL if provided
    if camera_type == "rtsp" and rtsp_url:
        config_path = Path("config/cameras.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            for cam in config['cameras']:
                if cam['id'] == 'camera_1':
                    cam['rtsp_url'] = rtsp_url
                    cam['enabled'] = True
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            global camera_manager
            camera_manager = CameraManager()
    
    if camera_manager:
        camera_manager.start_all()
    
    return {"status": "started", "source": f"camera_{camera_type}"}

@app.post("/api/camera/stop")
async def stop_camera():
    """Stop camera stream"""
    if camera_manager:
        camera_manager.stop_all()
    source_manager.active_source = None
    return {"status": "stopped"}


# WEBSOCKET Real-time detection updates

@app.websocket("/ws/detection")
async def websocket_detection(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # Handle control messages with timeout
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(), 
                    timeout=0.01
                )
                msg_type = message.get("type")
                
                if msg_type == "update_threshold":
                    new_threshold = float(message["threshold"])
                    inference_engine.threshold = new_threshold
                    print(f"🎚️ Threshold updated to {new_threshold}")
                    continue
                elif msg_type == "update_alert_email":
                    alert_system.alert_recipient = message["email"]
                    print(f"📧 Alert email updated to {message['email']}")
                    continue
                elif msg_type == "start_camera":
                    source_manager.switch_to_camera()
                    if camera_manager:
                        camera_manager.start_all()
                    continue
                elif msg_type == "stop_camera":
                    if camera_manager:
                        camera_manager.stop_all()
                    source_manager.active_source = None
                    continue
            except asyncio.TimeoutError:
                pass  # No message, continue with inference
            except WebSocketDisconnect:
                break
            
            # Process frames ONLY if camera source is active
            if source_manager.active_source == "camera" and camera_manager:
                frame = camera_manager.get_frame("camera_1")
                
                if frame is not None:
                    is_camera_motion = motion_filter.is_camera_motion(frame)
                    alert_system.add_frame_to_buffer(frame)
                    
                    score, is_alert = inference_engine.predict(frame)
                    
                    # Convert NumPy types for JSON serialization
                    is_camera_motion = bool(is_camera_motion)
                    is_alert = bool(is_alert) if is_alert is not None else False
                    
                    # Suppress alerts during camera motion
                    if is_camera_motion and score is not None:
                        score = max(0.0, score * 0.3)
                        is_alert = False
                    
                    if score is not None:
                        # Add to live history for graph
                        score_history.append({
                            "time": datetime.now().strftime("%H:%M:%S"), 
                            "score": float(score)
                        })
                        
                        # Encode frame as Base64 JPEG
                        _, buffer = cv2.imencode(
                            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                        )
                        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                        
                        # Build response
                        response = {
                            "timestamp": datetime.now().isoformat(),
                            "anomaly_score": float(score),
                            "is_alert": is_alert,
                            "camera_id": "camera_1",
                            "frame": jpg_as_text,
                            "camera_motion": is_camera_motion,
                            "active_source": "camera",
                            "score_history": list(score_history) + list(upload_score_history)[-10:]
                        }
                        
                        # ✅ EVENT-BASED ALERTING: One clip per anomaly event
                        if (is_alert and not is_camera_motion and 
                            alert_system.should_start_new_alert_event(
                                score, inference_engine.threshold
                            )):
                            clip_path = alert_system.save_alert_clip(
                                "camera_1", "Main Entrance", score
                            )
                            alert_system.log_alert(
                                "camera_1", "Main Entrance", score, clip_path
                            )
                            alert_system.send_email_alert(
                                camera_name="Main Entrance",
                                score=score,
                                clip_path=clip_path,
                                threshold=inference_engine.threshold,
                                location="Office"
                            )
                            response["alert_triggered"] = True
                            response["clip_path"] = str(clip_path) if clip_path else None
                        
                        await websocket.send_json(response)
            
            await asyncio.sleep(0.05)  # Prevent CPU overload
            
    except asyncio.CancelledError:
        print("🔌 WebSocket connection closed gracefully")
    except WebSocketDisconnect:
        print("🔌 Client disconnected")
    except Exception as e:
        print(f"⚠️ WebSocket error: {type(e).__name__}: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


