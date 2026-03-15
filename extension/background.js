/**
 * JobHunter Agent Chrome Extension - Background Service Worker
 *
 * Connects to the backend via WebSocket and relays CDP (Chrome DevTools Protocol)
 * commands between the backend and the user's browser via chrome.debugger API.
 */

// --- State ---
let ws = null;
let attachedTabId = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY = 1000; // 1s, exponential backoff

// --- Config ---
const BACKEND_URLS = {
  production: "wss://backend-production-cf43.up.railway.app",
  staging: "wss://backend-staging-a1c9.up.railway.app",
  local: "ws://localhost:8000",
};

// --- Helpers ---

function getBackendUrl() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["environment"], (result) => {
      const env = result.environment || "production";
      resolve(BACKEND_URLS[env] || BACKEND_URLS.production);
    });
  });
}

function getAuthToken() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["authToken"], (result) => {
      resolve(result.authToken || null);
    });
  });
}

function updateStatus(status, message) {
  chrome.storage.local.set({ connectionStatus: status, statusMessage: message });
  // Notify popup if open
  chrome.runtime.sendMessage({ type: "status_update", status, message }).catch(() => {});
}

// --- CDP Event Listener ---

function onDebuggerEvent(source, method, params) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "cdp_event",
      method,
      params: params || {},
      tabId: source.tabId,
    }));
  }
}

function onDebuggerDetach(source, reason) {
  if (source.tabId === attachedTabId) {
    attachedTabId = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "tab_detached",
        tabId: source.tabId,
        reason,
      }));
    }
  }
}

// --- Debugger Attach/Detach ---

async function attachToTab(tabId) {
  if (attachedTabId === tabId) return;

  // Detach from previous tab if any
  if (attachedTabId !== null) {
    try {
      await chrome.debugger.detach({ tabId: attachedTabId });
    } catch (e) {
      // Tab may already be closed
    }
  }

  await chrome.debugger.attach({ tabId }, "1.3");
  attachedTabId = tabId;

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "tab_ready", tabId }));
  }
}

async function detachFromTab() {
  if (attachedTabId !== null) {
    try {
      await chrome.debugger.detach({ tabId: attachedTabId });
    } catch (e) {
      // Already detached
    }
    attachedTabId = null;
  }
}

// --- CDP Command Execution ---

async function executeCdpCommand(id, method, params) {
  if (attachedTabId === null) {
    return { id, type: "cdp_error", error: "No tab attached" };
  }

  try {
    const result = await chrome.debugger.sendCommand(
      { tabId: attachedTabId },
      method,
      params || {}
    );
    return { id, type: "cdp_response", result: result || {} };
  } catch (error) {
    return { id, type: "cdp_error", error: error.message || String(error) };
  }
}

// --- WebSocket Connection ---

async function connect() {
  const token = await getAuthToken();
  if (!token) {
    updateStatus("disconnected", "No auth token. Log in at jobhunteragent.com first.");
    return;
  }

  const baseUrl = await getBackendUrl();
  const url = `${baseUrl}/ws/extension/connect?token=${encodeURIComponent(token)}`;

  updateStatus("connecting", "Connecting to JobHunter Agent...");

  try {
    ws = new WebSocket(url);
  } catch (e) {
    updateStatus("error", `Connection failed: ${e.message}`);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    reconnectAttempts = 0;
    updateStatus("connected", "Connected to JobHunter Agent");
  };

  ws.onmessage = async (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    switch (data.type) {
      case "connected":
        updateStatus("connected", `Connected as user ${data.user_id}`);
        break;

      case "cdp_command": {
        const response = await executeCdpCommand(data.id, data.method, data.params);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify(response));
        }
        break;
      }

      case "navigate": {
        // Server asks us to open a URL in a new tab
        const tab = await chrome.tabs.create({ url: data.url, active: true });
        try {
          // Wait a moment for tab to start loading before attaching
          await new Promise((r) => setTimeout(r, 500));
          await attachToTab(tab.id);
        } catch (e) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "navigate_error",
              error: e.message,
              tabId: tab.id,
            }));
          }
        }
        break;
      }

      case "attach_tab": {
        try {
          await attachToTab(data.tabId);
        } catch (e) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "cdp_error",
              id: data.id || 0,
              error: `Failed to attach: ${e.message}`,
            }));
          }
        }
        break;
      }

      case "detach": {
        await detachFromTab();
        break;
      }

      case "pong":
        break;

      default:
        break;
    }
  };

  ws.onerror = (event) => {
    updateStatus("error", "WebSocket error");
  };

  ws.onclose = (event) => {
    ws = null;
    if (event.code === 4001) {
      updateStatus("error", "Authentication failed. Please re-login.");
      return; // Don't reconnect for auth failures
    }
    updateStatus("disconnected", "Disconnected from server");
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    updateStatus("error", "Max reconnect attempts reached. Click to retry.");
    return;
  }

  const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
  reconnectAttempts++;
  updateStatus("reconnecting", `Reconnecting in ${Math.round(delay / 1000)}s...`);

  setTimeout(() => {
    connect();
  }, delay);
}

function disconnect() {
  if (ws) {
    ws.close(1000, "User disconnected");
    ws = null;
  }
  detachFromTab();
  updateStatus("disconnected", "Disconnected");
  reconnectAttempts = MAX_RECONNECT_ATTEMPTS; // Prevent auto-reconnect
}

// --- Keepalive ---

setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ping" }));
  }
}, 30000); // Every 30s

// --- Event Listeners ---

chrome.debugger.onEvent.addListener(onDebuggerEvent);
chrome.debugger.onDetach.addListener(onDebuggerDetach);

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "connect":
      reconnectAttempts = 0;
      connect();
      sendResponse({ ok: true });
      break;
    case "disconnect":
      disconnect();
      sendResponse({ ok: true });
      break;
    case "get_status":
      chrome.storage.local.get(["connectionStatus", "statusMessage"], (result) => {
        sendResponse({
          status: result.connectionStatus || "disconnected",
          message: result.statusMessage || "Not connected",
        });
      });
      return true; // Async response
    case "set_token":
      chrome.storage.local.set({ authToken: message.token }, () => {
        sendResponse({ ok: true });
        // Auto-connect after setting token
        reconnectAttempts = 0;
        connect();
      });
      return true;
    case "set_environment":
      chrome.storage.local.set({ environment: message.environment }, () => {
        sendResponse({ ok: true });
      });
      return true;
  }
});

// Auto-connect on install/startup
chrome.runtime.onInstalled.addListener(() => {
  updateStatus("disconnected", "Extension installed. Log in to connect.");
});

chrome.runtime.onStartup.addListener(() => {
  connect();
});

// Also try connecting immediately (for when service worker restarts)
connect();
