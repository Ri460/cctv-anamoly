"""
Real-Time Anomaly Detection Inference Engine
Handles frame processing and model inference
"""

import cv2
import torch
import timm
import numpy as np
from torchvision import transforms
from collections import deque
import time
import yaml
from pathlib import Path

class InferenceEngine:
    def __init__(self, model_path, config_path="config/system.yaml"):
        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.device = self.config['inference']['device']
        self.window_size = self.config['inference']['window_size']
        self.threshold = self.config['inference']['threshold']
        
        # Temporal smoothing parameters (prevents "blinking" alerts)
        self.temporal_trigger_frames = self.config['inference'].get('temporal_trigger_frames', 3)
        self.temporal_clear_frames = self.config['inference'].get('temporal_clear_frames', 5)
        self.alert_state = False  # Current smoothed alert state
        self.consecutive_count = 0  # Frame counter for state transitions
        print(f"✅ Temporal smoothing: trigger={self.temporal_trigger_frames} frames, clear={self.temporal_clear_frames} frames")
                
        # Initialize buffers
        self.frame_buffer = deque(maxlen=self.window_size)
        self.feature_buffer = deque(maxlen=self.window_size)
        
        # Load models
        print("Loading models...")
        self._load_models(model_path)
        print("Models loaded successfully!")
    
    def _load_models(self, model_path):
        """Load EfficientNet and LSTM models"""
        # Load EfficientNet-B0
        self.cnn = timm.create_model(
            "efficientnet_b0", 
            pretrained=True, 
            num_classes=0
        ).eval().to(self.device)
        
        # Load LSTM model
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        
        # Import model class
        from backend.models.lstm_model import AttentionLSTMAnomaly
        self.lstm = AttentionLSTMAnomaly().to(self.device)
        self.lstm.load_state_dict(checkpoint['model_state_dict'])
        self.lstm.eval()
        
        # Setup transform
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406], 
                std=[0.229, 0.224, 0.225]
            )
        ])
    
    def preprocess_frame(self, frame):
        """Convert BGR frame to normalized tensor"""
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        tensor = self.transform(frame).unsqueeze(0)
        return tensor.to(self.device)
    
    def extract_features(self, frame):
        """Extract features using EfficientNet"""
        tensor = self.preprocess_frame(frame)
        with torch.no_grad():
            feature = self.cnn(tensor)
        return feature.cpu()  # Keep on CPU to save GPU memory
    
    def predict(self, frame):
        """
        Process frame and return anomaly score
        Returns: (score, is_alert) where is_alert is TEMPORALLY SMOOTHED
        """
        # Extract features
        feature = self.extract_features(frame)
        
        # Update buffers
        self.frame_buffer.append(frame.copy())
        self.feature_buffer.append(feature)
        
        #  SINGLE INFERENCE BLOCK WITH TEMPORAL SMOOTHING
        if len(self.feature_buffer) >= 10 and len(self.feature_buffer) % 5 == 0:
            # Concatenate features: each is [1, 1280] → [T, 1280]
            features_tensor = torch.cat(list(self.feature_buffer), dim=0)
            # Add batch dimension: [1, T, 1280]
            features_tensor = features_tensor.unsqueeze(0).to(self.device)
            lengths = torch.tensor([features_tensor.shape[1]]).to(self.device)
            
            with torch.no_grad():
                logits, _ = self.lstm(features_tensor, lengths)
                score = torch.sigmoid(logits).item()
            
            #  TEMPORAL SMOOTHING: State machine to prevent "blinking" alerts
            raw_alert = score > self.threshold
            
            if self.alert_state:  # Currently in ALERT state
                if not raw_alert:
                    self.consecutive_count += 1
                    if self.consecutive_count >= self.temporal_clear_frames:
                        self.alert_state = False  # Clear alert after sustained normal frames
                        self.consecutive_count = 0
                else:
                    self.consecutive_count = 0  # Reset counter (still alerting)
            else:  # Currently in NORMAL state
                if raw_alert:
                    self.consecutive_count += 1
                    if self.consecutive_count >= self.temporal_trigger_frames:
                        self.alert_state = True  # Trigger alert after sustained anomaly frames
                        self.consecutive_count = 0
                else:
                    self.consecutive_count = 0  # Reset counter (still normal)
            
            # Return raw score + SMOOTHED alert state
            return score, self.alert_state
        
        #  ALWAYS RETURN TUPLE (prevents unpacking errors in app.py)
        return None, self.alert_state  # Preserve current state when no inference runs
    
    def get_attention_heatmap(self, frame):
        """Generate attention heatmap for visualization"""
        # This is a placeholder - implement based on your LSTM attention
        height, width = frame.shape[:2]
        heatmap = np.zeros((height, width), dtype=np.uint8)
        return heatmap

# Test the engine
if __name__ == "__main__":
    engine = InferenceEngine(
        model_path="backend/models/best_lstm_multidataset.pt"
    )
    # engine = InferenceEngine(
    #     model_path="backend/models/best_lstm_multidataset_robust.pt"
    # )
    print("✅ Inference Engine initialized successfully!")