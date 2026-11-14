"use strict";

async function showResponse(path, targetId) {
  const target = document.getElementById(targetId);
  try {
    const response = await fetch(path);
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `HTTP ${response.status}`);
    target.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    target.textContent = `Local API response unavailable: ${error.message}`;
    target.classList.add("error");
  }
}

Promise.all([showResponse("/ml/traffic", "traffic"), showResponse("/ml/anomaly", "anomaly")]);
