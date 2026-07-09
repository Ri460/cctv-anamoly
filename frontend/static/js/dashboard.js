// CCTV Anomaly Detection - Dashboard Logic

let ws = null;
let canvas = null;
let ctx = null;
let fpsCounter = 0;
let anomalyChart = null;
let currentSource = null;

document.addEventListener("DOMContentLoaded", () => {
  console.log("🚀 CCTV Dashboard initialized");

  canvas = document.getElementById("videoCanvas");
  ctx = canvas.getContext("2d");

  initInputSelection();
  initCameraControls();
  initThresholdControl();
  initEmailConfig();
  initChart();
  initUpload();
  connectWebSocket();

  setInterval(updateFPS, 1000);
});

//  INPUT SELECTION
function initInputSelection() {
  const cards = document.querySelectorAll(".input-card");
  const sections = document.querySelectorAll(".input-section");

  cards.forEach((card) => {
    card.addEventListener("click", () => {
      if (currentSource === "camera") stopCameraStream();
      cards.forEach((c) => c.classList.remove("active"));
      sections.forEach((s) => s.classList.remove("active"));
      card.classList.add("active");
      document.getElementById(card.dataset.target).classList.add("active");
    });
  });

  document.getElementById("cameraType").addEventListener("change", (e) => {
    const rtspGroup = document.getElementById("rtspUrlGroup");
    rtspGroup.style.display = e.target.value === "rtsp" ? "block" : "none";
  });
}

//  CAMERA CONTROLS
function initCameraControls() {
  const startBtn = document.getElementById("startStreamBtn");
  const stopBtn = document.getElementById("stopStreamBtn");

  startBtn.addEventListener("click", async () => {
    if (currentSource === "upload")
      showNotification("Stopping video upload...", "info");

    const cameraType = document.getElementById("cameraType").value;
    const rtspUrl = document.getElementById("rtspUrl").value;

    try {
      const response = await fetch("/api/camera/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_type: cameraType, rtsp_url: rtspUrl }),
      });
      const result = await response.json();

      if (result.status === "started") {
        currentSource = "camera";
        startBtn.disabled = true;
        stopBtn.disabled = false;
        updateStatus("Streaming", "success");
        showNotification("Camera stream started", "success");
      }
    } catch (error) {
      console.error("Error starting camera:", error);
      showNotification("Failed to start camera stream", "error");
    }
  });

  stopBtn.addEventListener("click", async () => {
    await stopCameraStream();
  });

  document.getElementById("snapshotBtn").addEventListener("click", () => {
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
}

async function stopCameraStream() {
  try {
    const response = await fetch("/api/camera/stop", { method: "POST" });
    const result = await response.json();
    if (result.status === "stopped") {
      currentSource = null;
      document.getElementById("startStreamBtn").disabled = false;
      document.getElementById("stopStreamBtn").disabled = true;
      updateStatus("Stopped", "info");
      showNotification("Camera stream stopped", "info");
    }
  } catch (error) {
    console.error("Error stopping camera:", error);
  }
}

//  THRESHOLD SLIDER
function initThresholdControl() {
  const slider = document.getElementById("thresholdSlider");
  const display = document.getElementById("thresholdValue");

  slider.addEventListener("input", (e) => {
    const value = parseFloat(e.target.value);
    display.textContent = value.toFixed(2);
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "update_threshold", threshold: value }));
    }
  });
}

// EMAIL CONFIG
function initEmailConfig() {
  const saved = localStorage.getItem("alertEmail");
  if (saved) document.getElementById("alertEmail").value = saved;
}

function updateAlertEmail() {
  const email = document.getElementById("alertEmail").value;
  if (!email.includes("@")) {
    showNotification("Please enter a valid email", "error");
    return;
  }
  localStorage.setItem("alertEmail", email);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "update_alert_email", email }));
    showNotification(`Alerts will be sent to ${email}`, "success");
  }
}

//  CHART.JS GRAPH
function initChart() {
  const ctx = document.getElementById("anomalyChart");
  if (!ctx) return;

  anomalyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Anomaly Score",
          data: [],
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          tension: 0.3,
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 0 },
      scales: {
        y: {
          min: 0,
          max: 1,
          grid: { color: "#334155" },
          ticks: { color: "#94a3b8" },
        },
        x: {
          grid: { color: "#334155" },
          ticks: { color: "#94a3b8", maxTicksLimit: 8 },
        },
      },
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
    },
  });
}

//  UPLOAD HANDLING
function initUpload() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const browseBtn = document.getElementById("browseBtn");

  browseBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files[0]) handleFileUpload(e.target.files[0]);
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.style.borderColor = "#6366f1";
    dropZone.style.backgroundColor = "rgba(99, 102, 241, 0.1)";
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)";
    dropZone.style.backgroundColor = "";
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.style.borderColor = "rgba(99, 102, 241, 0.4)";
    dropZone.style.backgroundColor = "";
    if (e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]);
  });
}

async function handleFileUpload(file) {
  if (currentSource === "camera") {
    await stopCameraStream();
    showNotification("Switching to video upload...", "info");
  }

  const formData = new FormData();
  formData.append("file", file);

  document.getElementById("uploadProgress").style.display = "block";
  document.getElementById("fileName").textContent = file.name;
  document.getElementById("fileSize").textContent = formatFileSize(file.size);

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (data.status === "processing") {
      currentSource = "upload";
      showNotification(data.message, "success");
    } else {
      showNotification(
        "Upload failed: " + (data.message || "Unknown error"),
        "error",
      );
    }
  } catch (err) {
    showNotification("Upload failed: " + err.message, "error");
  } finally {
    document.getElementById("uploadProgress").style.display = "none";
  }
}

function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

//  WEBSOCKET
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/detection`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("✅ WebSocket connected");
    updateStatus("Connected", "connected");
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };

  ws.onclose = () => {
    console.log("❌ WebSocket disconnected");
    updateStatus("Disconnected", "");
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = (error) => console.error("WebSocket error:", error);
}

function handleServerMessage(data) {
  if (data.frame) drawFrame(data.frame);
  if (data.anomaly_score !== undefined)
    updateScore(data.anomaly_score, data.is_alert);
  if (data.score_history && anomalyChart) {
    anomalyChart.data.labels = data.score_history.map((d) => d.time);
    anomalyChart.data.datasets[0].data = data.score_history.map((d) => d.score);
    anomalyChart.update();
  }
  if (data.alert_triggered) {
    showAlert(data.anomaly_score);
    addToAlertsList(data);
  }
  if (data.active_source) currentSource = data.active_source;
}

function drawFrame(frameData) {
  if (!frameData || !ctx || !canvas) return;
  const img = new Image();
  img.onload = () => {
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

function updateScore(score, isAlert) {
  document.getElementById("scoreValue").textContent = score.toFixed(2);
  const badge = document.getElementById("detectionStatus");
  if (isAlert) {
    badge.innerHTML =
      '<i class="fas fa-exclamation-triangle"></i><span>ALERT</span>';
    badge.className = "status-badge alert";
  } else {
    badge.innerHTML = '<i class="fas fa-check-circle"></i><span>Normal</span>';
    badge.className = "status-badge";
  }
}

function showAlert(score) {
  const overlay = document.getElementById("alertOverlay");
  document.getElementById("alertScore").textContent =
    `Score: ${score.toFixed(2)}`;
  overlay.classList.add("show");
  setTimeout(() => overlay.classList.remove("show"), 5000);
}

function dismissAlert() {
  document.getElementById("alertOverlay").classList.remove("show");
}

function saveClip() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "save_clip" }));
    showNotification("Clip saved", "success");
  }
}

function addToAlertsList(data) {
  const list = document.getElementById("alertsList");
  const empty = list.querySelector(".empty-state");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = `alert-item ${data.is_alert ? "" : "normal"}`;
  item.innerHTML = `
    <div class="alert-icon-small ${data.is_alert ? "" : "normal"}">
      <i class="fas ${data.is_alert ? "fa-exclamation-triangle" : "fa-check-circle"}"></i>
    </div>
    <div class="alert-details">
      <div class="alert-time">${new Date().toLocaleTimeString()}</div>
      <div class="alert-info">${data.is_alert ? "Anomaly Detected" : "Normal Activity"}</div>
    </div>
  `;
  list.insertBefore(item, list.firstChild);
  if (list.children.length > 10) list.removeChild(list.lastChild);
}

function updateStatus(text, type) {
  const dot = document.getElementById("statusDot");
  const txt = document.getElementById("statusText");
  const val = document.getElementById("statusValue");
  txt.textContent = text;
  val.textContent = text;
  if (type === "connected") {
    dot.className = "status-indicator connected";
  } else {
    dot.className = "status-indicator";
    dot.style.background = type === "success" ? "#10b981" : "#ef4444";
  }
}

function updateFPS() {
  const el = document.getElementById("fpsValue");
  if (el) {
    el.textContent = fpsCounter;
    fpsCounter = 0;
  }
}

function showNotification(message, type = "info") {
  const notification = document.createElement("div");
  notification.className = `notification ${type}`;
  notification.innerHTML = `
    <i class="fas ${getNotificationIcon(type)}"></i>
    <span>${message}</span>
    <button class="notification-close" onclick="this.parentElement.remove()">
      <i class="fas fa-times"></i>
    </button>
  `;
  document.body.appendChild(notification);
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
