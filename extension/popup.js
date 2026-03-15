/**
 * JobHunter Agent Chrome Extension - Popup UI
 */

const statusBadge = document.getElementById("statusBadge");
const statusText = document.getElementById("statusText");
const statusMessage = document.getElementById("statusMessage");
const tokenInput = document.getElementById("tokenInput");
const envSelect = document.getElementById("envSelect");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");

// --- UI Updates ---

function updateUI(status, message) {
  statusBadge.className = `status-badge ${status}`;
  statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
  statusMessage.textContent = message;

  if (status === "connected") {
    connectBtn.style.display = "none";
    disconnectBtn.style.display = "block";
  } else {
    connectBtn.style.display = "block";
    disconnectBtn.style.display = "none";
  }
}

// --- Load saved state ---

chrome.storage.local.get(["authToken", "environment"], (result) => {
  if (result.authToken) {
    tokenInput.value = "********"; // Don't show the actual token
  }
  if (result.environment) {
    envSelect.value = result.environment;
  }
});

// Get current status
chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
  if (response) {
    updateUI(response.status, response.message);
  }
});

// --- Event Listeners ---

connectBtn.addEventListener("click", () => {
  const token = tokenInput.value.trim();
  if (token && token !== "********") {
    // Save new token and connect
    chrome.runtime.sendMessage({ type: "set_token", token }, () => {});
  }

  // Save environment
  chrome.runtime.sendMessage(
    { type: "set_environment", environment: envSelect.value },
    () => {}
  );

  chrome.runtime.sendMessage({ type: "connect" });
  updateUI("connecting", "Connecting...");
});

disconnectBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" });
  updateUI("disconnected", "Disconnected by user");
});

// Listen for status updates from background
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "status_update") {
    updateUI(message.status, message.message);
  }
});
