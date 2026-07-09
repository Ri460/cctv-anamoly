// SMARTWATCH AI - MAIN APPLICATION LOGIC

// Global variables
let currentInputMode = "camera";
let isCameraActive = false;
let isRecording = false;
let ws = null;
let canvas = null;
let ctx = null;
let fpsCounter = 0;
let lastFrameTime = 0;

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  console.log("🚀 SmartWatch AI initialized");

  // Setup DOM elements
  canvas = document.getElementById("videoCanvas");
  ctx = canvas.getContext("2d");

  // Initialize components
  initInputSelection();
  initCameraControls();
  initThresholdControl();
  initWebSocket();

  // Start FPS counter
  setInterval(updateFPS, 1000);

  // Connect to server
  connectToServer();
});

// ===== INPUT SELECTION =====
function initInputSelection() {
  const inputCards = document.querySelectorAll(".input-card");
  const cameraSection = document.getElementById("cameraSection");
  const uploadSection = document.getElementById("uploadSection");

  inputCards.forEach((card) => {
    card.addEventListener("click", () => {
      // Remove active class from all cards
      inputCards.forEach((c) => c.classList.remove("active"));

      // Add active class to clicked card
      card.classList.add("active");

      // Show corresponding section
      if (card.dataset.type === "camera") {
        cameraSection.classList.add("active");
        uploadSection.classList.remove("active");
        currentInputMode = "camera";
      } else {
        uploadSection.classList.add("active");
        cameraSection.classList.remove("active");
        currentInputMode = "upload";
      }
    });
  });
}

// CAMERA CONTROLS
function initCameraControls() {
  const startBtn = document.getElementById("startCameraBtn");
  const stopBtn = document.getElementById("stopCameraBtn");
  const snapshotBtn = document.getElementById("snapshotBtn");
  const recordBtn = document.getElementById("recordBtn");
  const fullscreenBtn = document.getElementById("fullscreenBtn");

  // Start camera
  startBtn.addEventListener("click", async () => {
    const cameraType = document.getElementById("cameraType").value;
    const streamUrl = document.getElementById("streamUrl").value;

    try {
      // Send start command to backend via WebSocket
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            type: "start_camera",
            cameraType: cameraType,
            streamUrl: streamUrl,
          }),
        );

        startBtn.disabled = true;
        stopBtn.disabled = false;
        isCameraActive = true;

        showNotification("Camera stream started", "success");
      }
    } catch (error) {
      console.error("Error starting camera:", error);
      showNotification("Failed to start camera stream", "error");
    }
  });

  // Stop camera
  stopBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop_camera" }));

      startBtn.disabled = false;
      stopBtn.disabled = true;
      isCameraActive = false;

      showNotification("Camera stream stopped", "info");
    }
  });

  // Take snapshot
  snapshotBtn.addEventListener("click", () => {
    if (!canvas) return;

    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `snapshot_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);

      showNotification("Snapshot saved", "success");
    }, "image/png");
  });

  // Toggle recording
  recordBtn.addEventListener("click", () => {
    isRecording = !isRecording;
    recordBtn.innerHTML = isRecording
      ? '<i class="fas fa-stop-circle"></i>'
      : '<i class="fas fa-circle"></i>';
    recordBtn.style.color = isRecording ? "#ef4444" : "#94a3b8";

    showNotification(
      isRecording ? "Recording started" : "Recording stopped",
      "info",
    );
  });

  // Toggle fullscreen
  fullscreenBtn.addEventListener("click", () => {
    const videoContainer = document.getElementById("videoContainer");

    if (!document.fullscreenElement) {
      videoContainer.requestFullscreen().catch((err) => {
        console.error("Error attempting to enable fullscreen:", err);
      });
    } else {
      document.exitFullscreen();
    }
  });
}

//  THRESHOLD CONTROL
function initThresholdControl() {
  const thresholdSlider = document.getElementById("thresholdSlider");
  const thresholdDisplay = document.getElementById("thresholdDisplay");
  const thresholdValue = document.getElementById("thresholdValue");

  thresholdSlider.addEventListener("input", (e) => {
    const value = parseFloat(e.target.value);
    thresholdDisplay.textContent = value.toFixed(2);
    thresholdValue.textContent = value.toFixed(2);

    // Send to backend
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "update_threshold",
          threshold: value,
        }),
      );
    }
  });
}

//  WEBSOCKET COMMUNICATION
function initWebSocket() {
  // WebSocket connection is handled in websocket.js
}

function connectToServer() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/detection`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("✅ WebSocket connected");
    updateStatus("connected", "Connected");
    showNotification("Connected to server", "success");
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };

  ws.onclose = () => {
    console.log("❌ WebSocket disconnected");
    updateStatus("disconnected", "Disconnected");
    setTimeout(connectToServer, 3000);
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };
}

function handleServerMessage(data) {
  // Draw video frame
  if (data.frame) {
    drawFrame(data.frame);
  }

  // Update anomaly score
  if (data.anomaly_score !== undefined) {
    updateScore(data.anomaly_score, data.is_alert);
  }

  // Handle alerts
  if (data.alert_triggered) {
    showAlert(data.anomaly_score);
    addToTimeline(data);
  }

  // Update camera motion status
  if (data.camera_motion !== undefined) {
    updateCameraMotionStatus(data.camera_motion);
  }
}

//  VIDEO RENDERING
function drawFrame(frameData) {
  if (!frameData || !ctx || !canvas) return;

  const img = new Image();
  img.onload = () => {
    // Maintain aspect ratio
    const scaleX = canvas.width / img.width;
    const scaleY = canvas.height / img.height;
    const scale = Math.min(scaleX, scaleY);
    const x = (canvas.width - img.width * scale) / 2;
    const y = (canvas.height - img.height * scale) / 2;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, x, y, img.width * scale, img.height * scale);

    fpsCounter++;
  };
  img.src = `data:image/jpeg;base64,${frameData}`;
}

//  SCORE & STATUS UPDATES
function updateScore(score, isAlert) {
  const scoreValue = document.getElementById("scoreValue");
  const statusBadge = document.getElementById("detectionStatus");

  scoreValue.textContent = score.toFixed(2);

  if (isAlert) {
    statusBadge.innerHTML =
      '<i class="fas fa-exclamation-triangle"></i> <span>ALERT</span>';
    statusBadge.className = "status-badge alert";
  } else {
    statusBadge.innerHTML =
      '<i class="fas fa-check-circle"></i> <span>Normal</span>';
    statusBadge.className = "status-badge";
  }
}

function showAlert(score) {
  const overlay = document.getElementById("alertOverlay");
  const scoreElement = document.getElementById("alertScore");

  scoreElement.textContent = `Anomaly Score: ${score.toFixed(2)}`;
  overlay.classList.add("show");

  // Auto-dismiss after 5 seconds
  setTimeout(() => {
    overlay.classList.remove("show");
  }, 5000);
}

function dismissAlert() {
  document.getElementById("alertOverlay").classList.remove("show");
}

function saveAlertClip() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "save_clip" }));
    showNotification("Alert clip saved", "success");
  }
}

//  TIMELINE UPDATES
function addToTimeline(data) {
  const timeline = document.getElementById("alertsTimeline");
  const emptyState = timeline.querySelector(".empty-state");

  if (emptyState) {
    emptyState.remove();
  }

  const alertItem = document.createElement("div");
  alertItem.className = `alert-item ${data.is_alert ? "" : "normal"}`;
  alertItem.innerHTML = `
        <div class="alert-icon-timeline ${data.is_alert ? "" : "normal"}">
            <i class="fas ${data.is_alert ? "fa-exclamation-triangle" : "fa-check-circle"}"></i>
        </div>
        <div class="alert-details">
            <div class="alert-time">${new Date().toLocaleTimeString()}</div>
            <div class="alert-info">${data.is_alert ? "Anomaly Detected" : "Normal Activity"}</div>
        </div>
        <div class="alert-score-timeline ${data.is_alert ? "" : "normal"}">
            Score: ${data.anomaly_score.toFixed(2)}
        </div>
    `;

  timeline.insertBefore(alertItem, timeline.firstChild);

  // Limit to 10 items
  if (timeline.children.length > 10) {
    timeline.removeChild(timeline.lastChild);
  }
}

//  STATUS UPDATES
function updateStatus(status, text) {
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");

  if (status === "connected") {
    statusDot.className = "status-dot connected";
    statusText.textContent = "Connected";
  } else {
    statusDot.className = "status-dot";
    statusText.textContent = "Disconnected";
  }
}

function updateCameraMotionStatus(isMotion) {
  // Optional: Show camera motion indicator
}

//  FPS COUNTER
function updateFPS() {
  const fpsElement = document.getElementById("fpsValue");
  if (fpsElement) {
    fpsElement.textContent = fpsCounter;
    fpsCounter = 0;
  }
}

//  NOTIFICATIONS
function showNotification(message, type = "info") {
  // Create notification element
  const notification = document.createElement("div");
  notification.className = `notification ${type}`;
  notification.innerHTML = `
        <i class="fas ${getNotificationIcon(type)}"></i>
        <span>${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;

  // Add to body
  document.body.appendChild(notification);

  // Auto-remove after 3 seconds
  setTimeout(() => {
    notification.classList.add("fade-out");
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

function getNotificationIcon(type) {
  const icons = {
    success: "fa-check-circle",
    error: "fa-exclamation-circle",
    info: "fa-info-circle",
    warning: "fa-exclamation-triangle",
  };
  return icons[type] || "fa-info-circle";
}

//  CAMERA TYPE CHANGE
document.getElementById("cameraType")?.addEventListener("change", (e) => {
  const streamUrlGroup = document.getElementById("streamUrlGroup");
  const streamUrlInput = document.getElementById("streamUrl");

  if (e.target.value === "webcam") {
    streamUrlInput.value = "0";
    streamUrlGroup.style.display = "none";
  } else if (e.target.value === "webcam1") {
    streamUrlInput.value = "1";
    streamUrlGroup.style.display = "none";
  } else {
    streamUrlGroup.style.display = "block";
    streamUrlInput.value = "";
    streamUrlInput.placeholder =
      e.target.value === "rtsp"
        ? "rtsp://192.168.1.100:554/stream"
        : "http://192.168.1.100/video";
  }
});
