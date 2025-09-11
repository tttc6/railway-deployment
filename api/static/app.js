async function startBot() {
  const response = await fetch("/api/bot/start", { method: "POST" });
  const result = await response.json();
  updateStatus();
}

async function stopBot() {
  const response = await fetch("/api/bot/stop", { method: "POST" });
  const result = await response.json();
  updateStatus();
}

async function updateStatus() {
  const response = await fetch("/api/bot/status");
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
}

// Update status every 5 seconds
setInterval(updateStatus, 5000);
updateStatus();
