"""
Camera Stream Manager
Handles RTSP/Webcam streams
"""

import cv2
import time
from threading import Thread, Event
import json
from pathlib import Path

class CameraStream:
    def __init__(self, camera_id, rtsp_url, name="Camera"):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.name = name
        self.cap = None
        self.running = False
        self.frame = None
        self.last_update = 0
        self.fps = 0
    
    def start(self):
        """Start camera stream in background thread"""
        if self.running:
            return
        
        # Open camera
        if self.rtsp_url.isdigit():
            self.cap = cv2.VideoCapture(int(self.rtsp_url))
        else:
            self.cap = cv2.VideoCapture(self.rtsp_url)
        
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {self.rtsp_url}")
        
        # Set buffer size to reduce latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.running = True
        self.thread = Thread(target=self._update, daemon=True)
        self.thread.start()
        print(f"✅ Camera '{self.name}' started")
    
    def _update(self):
        """Background thread to read frames"""
        prev_time = time.time()
        frame_count = 0
        
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
                self.last_update = time.time()
                
                # Calculate FPS
                frame_count += 1
                curr_time = time.time()
                if curr_time - prev_time >= 1.0:
                    self.fps = frame_count
                    frame_count = 0
                    prev_time = curr_time
    
    def read(self):
        """Get latest frame"""
        return self.frame if self.frame is not None else None
    
    def stop(self):
        """Stop camera stream"""
        self.running = False
        if self.cap:
            self.cap.release()
        print(f"⏹️  Camera '{self.name}' stopped")

class CameraManager:
    def __init__(self, config_file="config/cameras.json"):
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        self.cameras = {}
        for cam_config in config['cameras']:
            if cam_config['enabled']:
                self.cameras[cam_config['id']] = CameraStream(
                    camera_id=cam_config['id'],
                    rtsp_url=cam_config['rtsp_url'],
                    name=cam_config['name']
                )
    
    def start_all(self):
        """Start all enabled cameras"""
        for camera in self.cameras.values():
            camera.start()
    
    def stop_all(self):
        """Stop all cameras"""
        for camera in self.cameras.values():
            camera.stop()
    
    def get_frame(self, camera_id):
        """Get frame from specific camera"""
        if camera_id in self.cameras:
            return self.cameras[camera_id].read()
        return None
    
    def get_status(self):
        """Get status of all cameras"""
        return {
            cam_id: {
                "name": cam.name,
                "running": cam.running,
                "fps": cam.fps
            }
            for cam_id, cam in self.cameras.items()
        }

# Test camera manager
if __name__ == "__main__":
    manager = CameraManager()
    manager.start_all()
    
    try:
        while True:
            frame = manager.get_frame("camera_1")
            if frame is not None:
                cv2.imshow("Test", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()
        cv2.destroyAllWindows()