# CCTV Anomaly Detection Dashboard

A real-time video surveillance system that flags anomalous activity in CCTV footage using an attention-based BiLSTM deep learning model, served through a FastAPI backend with a live web dashboard.

**Live demo:** [cctv-anamoly.onrender.com](https://cctv-anamoly.onrender.com/)
**Repo:** [github.com/Ri460/cctv-anamoly](https://github.com/Ri460/cctv-anamoly)

> Note: the demo is hosted on Render's free tier, so the first load may take 30-60s to spin up, and live camera streaming will be limited to whatever camera/video source is reachable from the server.

---

## Overview

This project takes a live camera feed or an uploaded video, runs each frame through a trained anomaly-detection model, and streams the results to a browser dashboard in real time over WebSockets. When the anomaly score crosses a configurable threshold, the system saves a clip of the event, logs the alert, and can send an email notification.

Core capabilities:
- **Real-time inference** on a live camera (webcam or RTSP stream) or an uploaded video file
- **WebSocket streaming** of frames, anomaly scores, and alerts to the dashboard with minimal latency
- **Camera-motion filtering** using optical flow, so panning/shaking doesn't trigger false alerts
- **Event-based alerting** — one clip and one notification per anomaly event, not per frame
- **Adjustable detection threshold** and alert email, both configurable live from the dashboard
- **Alert history** with saved clips for later review

## How it works

1. A frame is pulled from the active source (camera or uploaded video) via `CameraManager`.
2. The frame is passed to `InferenceEngine`, which runs the trained model and returns an anomaly score.
3. `CameraMotionFilter` checks whether the frame-to-frame motion looks like camera movement (panning/shaking) rather than an actual event, using Lucas-Kanade optical flow, and suppresses false positives accordingly.
4. If the score crosses the threshold and it's the start of a new anomaly event, `AlertSystem` saves a video clip, logs the alert, and optionally emails a notification.
5. The frame, score, and alert state are pushed to the browser over a WebSocket (`/ws/detection`) and rendered live on the dashboard.

Only one source (camera or uploaded video) is ever active at a time — switching sources automatically stops the other.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, Uvicorn, WebSockets |
| ML / CV | PyTorch, TorchVision, timm, OpenCV, NumPy |
| Frontend | Jinja2 templates, HTML/CSS/JS |
| Config | YAML / JSON, python-dotenv |

The anomaly detection model is an **attention-based Bidirectional LSTM trained with focal loss**, designed to spot unusual events in surveillance video while staying robust to class imbalance (anomalies are rare compared to normal footage).

## Project structure

```
cctv-anamoly/
├── app.py                 # FastAPI app: routes, WebSocket, source/alert orchestration
├── backend/
│   ├── inference_engine.py   # Loads the model, runs per-frame predictions
│   ├── camera_manager.py     # Handles camera/RTSP capture
│   └── alert_system.py       # Alert logging, clip saving, email notifications
├── config/
│   └── cameras.json           # Camera source configuration
├── frontend/
│   ├── templates/              # Jinja2 HTML templates (dashboard UI)
│   └── static/                 # CSS/JS assets
├── setup_configs.py         # Initial config/setup helper
└── requirements.txt
```

## Getting started

### Prerequisites
- Python 3.9+ (see `.python-version`)
- A webcam, RTSP stream, or sample video file to test with
- A trained model checkpoint (see [Model](#model))

### Installation

```bash
git clone https://github.com/Ri460/cctv-anamoly.git
cd cctv-anamoly

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
MODEL_PATH=backend/models/best_lstm_multidataset.pt
```

Configure camera sources in `config/cameras.json` (RTSP URL, camera ID, enabled flag, etc.). You can also run `setup_configs.py` to generate a starter config.

### Run

```bash
python app.py
```

The dashboard will be available at **http://localhost:8000**.

### Usage
- **Live camera:** click "Start Camera" on the dashboard, or `POST /api/camera/start` with `camera_type` and optionally `rtsp_url`.
- **Upload a video:** use the upload option on the dashboard, or `POST /api/upload` with a video file — it's processed frame-by-frame in the background.
- **Adjust threshold / alert email:** send `update_threshold` / `update_alert_email` messages over the `/ws/detection` WebSocket, or use the dashboard controls.
- **View alerts:** `GET /api/alerts?limit=50` returns recent logged alerts with clip paths.

## API reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard UI |
| `/api/status` | GET | System + camera status |
| `/api/alerts` | GET | Recent alerts |
| `/api/upload` | POST | Upload and process a video file |
| `/api/camera/start` | POST | Start a camera source |
| `/api/camera/stop` | POST | Stop the active camera |
| `/ws/detection` | WebSocket | Live frames, scores, and alerts |

## Model

This system is built to plug in a pretrained anomaly-detection checkpoint (expected at the path set by `MODEL_PATH`). The reference model used during development is an attention-based BiLSTM with focal loss, trained for video anomaly detection and achieving strong AUC/F1 on held-out surveillance footage. Swap in your own checkpoint by pointing `MODEL_PATH` to it, as long as `InferenceEngine` is compatible with its input/output shape.

## Roadmap / ideas
- Multi-camera grid view
- Configurable alert channels beyond email (SMS, Slack, webhook)
- Dockerfile for one-command deployment
- Model retraining pipeline from logged alert clips

## License

MIT — see [LICENSE](https://github.com/Ri460/cctv-anamoly/blob/main/LICENSE).
