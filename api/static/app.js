// Global authentication state
let currentUser = null;

async function checkAuth() {
  try {
    const response = await fetch("/auth/user");
    if (response.ok) {
      currentUser = await response.json();
      showDashboard();
      return true;
    } else {
      currentUser = null;
      showLogin();
      return false;
    }
  } catch (error) {
    console.error("Authentication check failed:", error);
    currentUser = null;
    showLogin();
    return false;
  }
}

function showDashboard() {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("dashboard").style.display = "block";
  document.getElementById("logout-btn").style.display = "inline-block";
  
  // Update user info
  if (currentUser) {
    const userNameEl = document.getElementById("user-name");
    userNameEl.textContent = currentUser.name || currentUser.username || "Unknown User";
  }
  
  // Start status updates
  updateStatus();
}

function showLogin() {
  document.getElementById("dashboard").style.display = "none";
  document.getElementById("login-screen").style.display = "block";
  document.getElementById("logout-btn").style.display = "none";
  
  // Clear user info
  document.getElementById("user-name").textContent = "";
}

async function logout() {
  try {
    const response = await fetch("/auth/logout");
    if (response.ok) {
      currentUser = null;
      showLogin();
    } else {
      console.error("Logout failed");
    }
  } catch (error) {
    console.error("Logout error:", error);
  }
}

async function startBot() {
  try {
    const response = await fetch("/api/bot/start", { method: "POST" });
    if (response.status === 401) {
      // Unauthorized - redirect to login
      window.location.href = "/auth/login";
      return;
    }
    const result = await response.json();
    updateStatus();
  } catch (error) {
    console.error("Error starting bot:", error);
  }
}

async function stopBot() {
  try {
    const response = await fetch("/api/bot/stop", { method: "POST" });
    if (response.status === 401) {
      // Unauthorized - redirect to login
      window.location.href = "/auth/login";
      return;
    }
    const result = await response.json();
    updateStatus();
  } catch (error) {
    console.error("Error stopping bot:", error);
  }
}

async function updateStatus() {
  try {
    const response = await fetch("/api/bot/status");
    if (response.status === 401) {
      // Unauthorized - show login screen
      showLogin();
      return;
    }
    
    const status = await response.json();
    
    // Format the status for display
    let statusHtml = '<div class="status-display">';
    
    if (status.message) {
      statusHtml += `<div class="status-item"><strong>Status:</strong> ${status.message}</div>`;
    } else {
      statusHtml += `<div class="status-item"><strong>Running:</strong> ${status.running === 'True' ? 'Yes' : 'No'}</div>`;
      statusHtml += `<div class="status-item"><strong>PnL:</strong> $${parseFloat(status.pnl || 0).toFixed(2)}</div>`;
      statusHtml += `<div class="status-item"><strong>Positions:</strong> ${status.positions || 0}</div>`;
      
      // Convert UTC timestamp to local timezone
      if (status.timestamp) {
        const utcDate = new Date(status.timestamp);
        const localTimestamp = utcDate.toLocaleString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          timeZoneName: 'short'
        });
        statusHtml += `<div class="status-item"><strong>Last Updated:</strong> ${localTimestamp}</div>`;
      }
    }
    
    statusHtml += '</div>';
    document.getElementById("status").innerHTML = statusHtml;
  } catch (error) {
    console.error("Error updating status:", error);
  }
}

// Initialize app
document.addEventListener("DOMContentLoaded", async function() {
  const isAuthenticated = await checkAuth();
  
  if (isAuthenticated) {
    // Update status every 5 seconds if authenticated
    setInterval(updateStatus, 5000);
  }
});
