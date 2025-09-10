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
  document.getElementById("status").innerHTML =
    `<pre>${JSON.stringify(status, null, 2)}</pre>`;
}

// Update status every 5 seconds
setInterval(updateStatus, 5000);
updateStatus();
