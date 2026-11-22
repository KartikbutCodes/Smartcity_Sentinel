"use strict";

(() => {
  const ui = window.SentinelUI;
  const nodePositions = {
    Central: [130, 180],
    North: [320, 70],
    River: [320, 290],
    Market: [510, 180]
  };
  const sensorDefinitions = [
    ["power_kw", "POWER", "kW"],
    ["water_pressure_kpa", "WATER PRESSURE", "kPa"],
    ["bridge_vibration", "BRIDGE VIBRATION", "m/s²"],
    ["aqi", "AIR QUALITY", "AQI"],
    ["noise_db", "NOISE", "dB"],
    ["flood_level_m", "FLOOD LEVEL", "m"]
  ];
  let latestAlerts = [];
  let metricsCache = null;
  let reconnectDelay = 1000;
  let reconnectTimer = null;
  let socket = null;
  let sensorSignature = "";

  function svg(name, attributes = {}) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function displayValue(value, decimals = 2) {
    return Number.isFinite(Number(value)) ? Number(value).toFixed(decimals) : "—";
  }

  function severityName(alert) {
    const severity = Number(alert.severity);
    return severity >= 0.75 ? "HIGH" : severity >= 0.45 ? "MED" : "LOW";
  }

  function severityClass(alert) {
    const severity = Number(alert.severity);
    return severity >= 0.75 ? "high" : severity >= 0.45 ? "medium" : "low";
  }

  function alertTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "TIME UNKNOWN" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function renderCity(graph, route) {
    const edgeLayer = document.getElementById("city-edges");
    const routeLayer = document.getElementById("city-route");
    const markerLayer = document.getElementById("city-markers");
    const nodeLayer = document.getElementById("city-nodes");
    edgeLayer.replaceChildren();
    routeLayer.replaceChildren();
    markerLayer.replaceChildren();
    nodeLayer.replaceChildren();
    const seenEdges = new Set();
    Object.entries(graph).forEach(([from, edges]) => {
      Object.entries(edges).forEach(([to, distance]) => {
        const key = [from, to].sort().join("|");
        if (seenEdges.has(key) || !nodePositions[from] || !nodePositions[to]) return;
        seenEdges.add(key);
        const [x1, y1] = nodePositions[from];
        const [x2, y2] = nodePositions[to];
        edgeLayer.append(svg("line", { x1, y1, x2, y2, class: "city-edge" }));
        const label = svg("text", { x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 7, class: "edge-distance" });
        label.textContent = String(distance);
        edgeLayer.append(label);
      });
    });

    const points = Array.isArray(route.path) ? route.path.map((name) => nodePositions[name]).filter(Boolean) : [];
    if (points.length > 1) {
      routeLayer.append(svg("polyline", {
        points: points.map(([x, y]) => `${x},${y}`).join(" "),
        class: "route-line draw-on-scroll",
        "data-draw-path": ""
      }));
    }

    renderCityMarkers();
    ui.setText("route-summary", Array.isArray(route.path) ? `${route.path.join(" → ")} · ${route.distance} units` : "Route unavailable");
    ui.setText("map-state", `${Object.keys(graph).length} nodes · route and latest alert levels from the API`);
    ui.refreshDrawPaths();
  }

  function renderCityMarkers() {
    const markerLayer = document.getElementById("city-markers");
    const nodeLayer = document.getElementById("city-nodes");
    markerLayer.replaceChildren();
    const alertsByLocation = new Map();
    latestAlerts.forEach((alert) => {
      const location = String(alert.location || "");
      const previous = alertsByLocation.get(location);
      if (!previous || new Date(alert.timestamp).getTime() >= new Date(previous.timestamp).getTime()) {
        alertsByLocation.set(location, alert);
      }
    });
    Object.entries(nodePositions).forEach(([name, [x, y]]) => {
      let group = nodeLayer.querySelector(`[data-city="${name}"]`);
      if (!group) {
        group = svg("g", { "data-city": name });
        group.append(
          svg("circle", { cx: x, cy: y, r: 19, class: "node-pulse", "data-node-pulse": "" }),
          svg("circle", { cx: x, cy: y, r: 9, class: "city-node", "data-node-marker": "" }),
          svg("text", { x, y: y + 34, class: "marker-count", "data-node-level": "" }),
          svg("text", { x, y: y - 17, class: "node-label", "data-node-label": "" })
        );
        nodeLayer.append(group);
      }
      const alert = alertsByLocation.get(`${name === "Central" ? "Central Junction" : name === "North" ? "North Bridge" : name === "River" ? "River Ward" : "Market Square"}`);
      const severity = alert ? severityClass(alert) : "low";
      const pulse = group.querySelector("[data-node-pulse]");
      pulse.setAttribute("class", `node-pulse severity-${severity}`);
      pulse.setAttribute("visibility", alert ? "visible" : "hidden");
      group.querySelector("[data-node-marker]").setAttribute("class", `city-node severity-${severity}`);
      const level = group.querySelector("[data-node-level]");
      level.textContent = alert ? severityName(alert) : "";
      level.setAttribute("visibility", alert ? "visible" : "hidden");
      group.querySelector("[data-node-label]").textContent = name.toUpperCase();
    });
  }

  function renderAlertFeed(alerts, appendNew = false) {
    const feed = document.getElementById("alert-feed");
    const oldIds = new Set(Array.from(feed.querySelectorAll("[data-alert-id]"), (row) => row.dataset.alertId));
    const sorted = alerts.slice().sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    feed.replaceChildren();
    if (!sorted.length) {
      const empty = document.createElement("p");
      empty.className = "panel-state";
      empty.textContent = "The API returned no alerts.";
      feed.append(empty);
      return;
    }
    sorted.slice(0, 30).forEach((alert) => {
      const button = document.createElement("button");
      const level = severityClass(alert);
      button.type = "button";
      button.className = `alert-row severity-${level}${appendNew && !oldIds.has(String(alert.id)) ? " new-alert" : ""}`;
      button.dataset.alertId = String(alert.id || "");
      button.setAttribute("aria-label", `${severityName(alert)} ${alert.kind || "event"} at ${alert.location || "unknown location"}. View full record.`);

      const timing = document.createElement("span");
      timing.className = "alert-timing";
      const time = document.createElement("time");
      time.textContent = alertTime(alert.timestamp);
      const severity = document.createElement("strong");
      severity.className = `severity-label severity-${level}`;
      severity.textContent = severityName(alert);
      const bar = document.createElement("i");
      bar.className = "severity-bar";
      bar.style.setProperty("--severity-fill", `${Math.max(0, Math.min(1, Number(alert.severity) || 0)) * 100}%`);
      timing.append(time, severity, bar);

      const event = document.createElement("span");
      event.className = "alert-event";
      const kind = document.createElement("strong");
      kind.className = "alert-kind";
      kind.textContent = String(alert.kind || "event").replaceAll("_", " ");
      const location = document.createElement("span");
      location.className = "alert-location";
      location.textContent = alert.location || "Location not supplied";
      const description = document.createElement("span");
      description.className = "alert-description";
      description.textContent = alert.description || "No description supplied";
      event.append(kind, location, description);
      button.append(timing, event);
      feed.append(button);
    });
    ui.setText("feed-state", `${sorted.length} IN MEMORY`);
  }

  function showAlert(alert) {
    const dialog = document.getElementById("alert-detail");
    document.getElementById("alert-json").textContent = JSON.stringify(alert, null, 2);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else {
      dialog.setAttribute("open", "");
      dialog.addEventListener("click", function closeOnBackdrop(event) {
        if (event.target === dialog) {
          dialog.removeAttribute("open");
          dialog.removeEventListener("click", closeOnBackdrop);
        }
      });
    }
  }

  function sparkline(series, field, threshold) {
    const values = series.map((row) => Number(row[field])).filter(Number.isFinite);
    const svgRoot = svg("svg", { viewBox: "0 0 220 54", preserveAspectRatio: "none", class: "sparkline", role: "img", "aria-label": `${field} sensor history` });
    if (!values.length) return svgRoot;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = max - min || 1;
    const coords = values.map((value, index) => [
      4 + index * 212 / Math.max(1, values.length - 1),
      47 - ((value - min) / spread) * 40
    ]);
    if (Number.isFinite(threshold)) {
      const y = 47 - ((threshold - min) / spread) * 40;
      svgRoot.append(svg("line", { x1: 2, y1: y, x2: 218, y2: y, class: "flood-threshold" }));
    }
    svgRoot.append(svg("polyline", {
      points: coords.map(([x, y]) => `${x},${y}`).join(" "),
      class: "spark-line"
    }));
    const average = values.reduce((total, value) => total + value, 0) / values.length;
    const variance = values.reduce((total, value) => total + ((value - average) ** 2), 0) / values.length;
    const deviation = Math.sqrt(variance);
    coords.forEach(([x, y], index) => {
      if (deviation > 0 && Math.abs(values[index] - average) > 2 * deviation) {
        svgRoot.append(svg("circle", { cx: x, cy: y, r: 3, class: "spark-anomaly" }));
      }
    });
    const [currentX, currentY] = coords[coords.length - 1];
    svgRoot.append(svg("circle", { cx: currentX, cy: currentY, r: 3.2, class: "spark-current" }));
    return svgRoot;
  }

  function renderSensors(readings, environmentAlerts) {
    const grid = document.getElementById("sensor-grid");
    grid.replaceChildren();
    if (!Array.isArray(readings) || !readings.length) {
      ui.setText("sensor-history", "No sensor rows returned.");
      return;
    }
    const floodAlert = environmentAlerts.find((alert) => alert.kind === "flood_level_m");
    const threshold = floodAlert ? Number(floodAlert.threshold) : NaN;
    ui.setText("sensor-history", `${readings.length} generated observations · amber dots are >2σ · flood limit ${Number.isFinite(threshold) ? `${threshold} m` : "not returned"}`);
    sensorDefinitions.forEach(([field, label, unit]) => {
      const values = readings.map((row) => Number(row[field])).filter(Number.isFinite);
      const card = document.createElement("article");
      card.className = "sensor-readout";
      const labelRow = document.createElement("div");
      labelRow.className = "sensor-label-row";
      const heading = document.createElement("h3");
      heading.textContent = label;
      const unitNode = document.createElement("span");
      unitNode.className = "sensor-unit";
      unitNode.textContent = unit;
      labelRow.append(heading, unitNode);
      const current = document.createElement("p");
      current.className = "sensor-current";
      current.textContent = `${displayValue(values[values.length - 1], field === "flood_level_m" || field === "bridge_vibration" ? 3 : 1)} `;
      const suffix = document.createElement("small");
      suffix.textContent = unit;
      current.append(suffix);
      const chart = sparkline(readings, field, field === "flood_level_m" ? threshold : NaN);
      card.append(labelRow, current, chart);
      grid.append(card);
    });
    ui.refreshDrawPaths();
  }

  function renderCrowd(metrics) {
    const score = Number(metrics.crowd_risk);
    if (!Number.isFinite(score)) return;
    const normalized = Math.max(0, Math.min(1, score));
    const gauge = document.getElementById("gauge-value");
    gauge.style.strokeDashoffset = String(283 * (1 - normalized));
    gauge.classList.toggle("attention", normalized >= 0.6);
    ui.setText("gauge-label", normalized.toFixed(3));
    const grid = Array.isArray(metrics.density_grid) ? metrics.density_grid : [];
    ui.setText("crowd-state", `SOURCE VALUE ${normalized.toFixed(3)}${grid.length ? ` · GRID ${grid.length}×${grid[0].length}` : ""}`);
    ui.setText("crowd-explanation", normalized >= 0.6
      ? "Higher occupancy in the generated grid; this is not a safety assessment."
      : "Lower occupancy in the generated grid; this is not a safety assessment.");
  }

  function renderAnomaly(scores) {
    const output = document.getElementById("anomaly-readouts");
    output.replaceChildren();
    const rows = [
      ["ISOLATION SCORE", scores.isolation_forest, "A larger score means this sample is easier for the fitted trees to isolate."],
      ["RECONSTRUCTION ERROR", scores.autoencoder_reconstruction_error, "A larger error means the small autoencoder reconstructs this sample less closely."]
    ];
    rows.forEach(([label, value, explanation]) => {
      const row = document.createElement("div");
      row.className = "readout";
      const title = document.createElement("span");
      title.className = "readout-label";
      title.textContent = label;
      const number = document.createElement("b");
      number.textContent = displayValue(value, 4);
      const note = document.createElement("p");
      note.className = "readout-explanation";
      note.textContent = explanation;
      row.append(title, number, note);
      output.append(row);
    });
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return "—";
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(2)} MB`;
    if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(2)} KB`;
    return `${bytes.toFixed(0)} B`;
  }

  function renderEdge(data) {
    const ratio = Number(data.bandwidth_reduction_ratio);
    ui.setText("edge-ratio", Number.isFinite(ratio) ? `${(ratio * 100).toFixed(2)}% LESS UPLINK` : "COMPARISON UNAVAILABLE");
    const rows = [
      { key: "edge", label: "EDGE · LOG SCALE", bytes: Number(data.edge_uplink_bytes), latency: data.edge_latency_ms },
      { key: "cloud", label: "CLOUD · LOG SCALE", bytes: Number(data.cloud_uplink_bytes), latency: data.cloud_latency_ms }
    ];
    const max = Math.max(...rows.map((row) => row.bytes).filter(Number.isFinite), 1);
    const root = document.getElementById("edge-bars");
    root.replaceChildren();
    rows.forEach((row) => {
      const line = document.createElement("div");
      line.className = `edge-row ${row.key}`;
      const body = document.createElement("div");
      body.className = "edge-line";
      const label = document.createElement("span");
      label.className = "edge-label";
      label.textContent = row.label;
      const track = document.createElement("span");
      track.className = "edge-track";
      const fill = document.createElement("i");
      fill.className = "edge-fill";
      const width = Number.isFinite(row.bytes) ? Math.max(7, Math.log1p(row.bytes) / Math.log1p(max) * 100) : 0;
      fill.style.width = `${width}%`;
      track.append(fill);
      const bytes = document.createElement("b");
      bytes.textContent = formatBytes(row.bytes);
      const latency = document.createElement("small");
      latency.textContent = `NOMINAL ${displayValue(row.latency, 0)} ms`;
      body.append(label, track, bytes);
      line.append(body, latency);
      root.append(line);
    });
  }

  function renderAudit(result, metrics) {
    const root = document.getElementById("audit-chain");
    root.replaceChildren();
    const blocks = Array.isArray(result.blocks) ? result.blocks : [];
    blocks.slice(0, 5).forEach((block, index) => {
      const x = 5 + index * 103;
      if (index > 0) root.append(svg("line", { x1: x - 15, y1: 36, x2: x - 3, y2: 36, class: "hash-link draw-on-scroll", "data-draw-path": "" }));
      const group = svg("g", { class: "hash-block demo-chain" });
      group.append(svg("rect", { x, y: 7, width: 88, height: 58, rx: 5 }));
      const number = svg("text", { x: x + 44, y: 23, class: "hash-index" });
      number.textContent = `BLOCK ${block.number}`;
      const hash = svg("text", { x: x + 44, y: 37, class: "hash-short" });
      hash.textContent = String(block.hash || "").slice(0, 10);
      const caption = svg("text", { x: x + 44, y: 53, class: "hash-caption" });
      caption.textContent = "DEMO CHAIN";
      group.append(number, hash, caption);
      root.append(group);
    });
    const caught = result.valid_before_tamper === true && result.valid_after_tamper === false;
    const state = document.getElementById("audit-state");
    state.textContent = caught ? "TAMPER CAUGHT" : "CHECK FAILED";
    state.classList.toggle("is-invalid", !caught);
    ui.setText("audit-detail", `${blocks.length} temporary blocks · valid before edit / rejected after · metrics log ${metrics.audit_chain_valid ? "VALID" : "CHECK FAILED"}`);
    ui.refreshDrawPaths();
  }

  function renderMetrics(metrics) {
    metricsCache = metrics;
    ui.setNumber("alert-count", Number(metrics.alert_count) || 0, 0);
    const readings = metrics.sensor_readings || [];
    const signature = Array.isArray(readings) && readings.length
      ? `${readings.length}:${readings[0].timestamp}:${readings[readings.length - 1].timestamp}`
      : "empty";
    if (signature !== sensorSignature) {
      sensorSignature = signature;
      renderSensors(readings, metrics.environment_alerts || []);
    }
    renderCrowd(metrics);
    renderAnomaly(metrics.anomaly_scores || {});
    renderEdge(metrics.edge_cloud || {});
  }

  async function loadInitial() {
    try {
      const [alerts, metrics, graph, route, audit] = await Promise.all([
        ui.getJson("/alerts"), ui.getJson("/metrics"), ui.getJson("/city"), ui.getJson("/route"), ui.getJson("/tools/audit-chain")
      ]);
      latestAlerts = alerts;
      window.__sentinelCityGraph = graph;
      window.__sentinelRoute = route;
      renderAlertFeed(alerts);
      renderMetrics(metrics);
      renderCity(graph, route);
      renderAudit(audit, metrics);
      ui.setText("stream-state", "CONNECTING");
      ui.refreshNarrator();
    } catch (error) {
      document.getElementById("map-state").textContent = `Local API unavailable: ${error.message}`;
      document.getElementById("feed-state").textContent = "OFFLINE";
      document.getElementById("feed-state").classList.add("is-error");
    }
  }

  async function refreshMetrics() {
    try {
      const metrics = await ui.getJson("/metrics");
      renderMetrics(metrics);
    } catch (error) {
      ui.setText("sensor-history", `Metrics unavailable: ${error.message}`);
    }
  }

  function receiveAlert(alert) {
    latestAlerts = [alert, ...latestAlerts.filter((item) => item.id !== alert.id)];
    renderAlertFeed(latestAlerts, true);
    ui.setText("stream-state", "LIVE");
    ui.refreshNarrator();
    if (metricsCache) {
      const currentCount = Number(document.getElementById("alert-count").dataset.countTarget);
      if (Number.isFinite(currentCount)) ui.setNumber("alert-count", currentCount + 1, 0);
    }
    renderCityMarkers();
  }

  function connectSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/alerts`);
    socket.addEventListener("open", () => {
      reconnectDelay = 1000;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
      ui.setText("stream-state", "LIVE");
    });
    socket.addEventListener("message", (event) => {
      try {
        receiveAlert(JSON.parse(event.data));
      } catch {
        ui.setText("stream-state", "BAD MESSAGE");
      }
    });
    socket.addEventListener("close", () => {
      ui.setText("stream-state", "RECONNECTING");
      if (!reconnectTimer) {
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connectSocket();
        }, reconnectDelay);
        reconnectDelay = Math.min(30000, reconnectDelay * 2);
      }
    });
    socket.addEventListener("error", () => socket.close());
  }

  const feed = document.getElementById("alert-feed");
  feed.addEventListener("click", (event) => {
    const row = event.target.closest("[data-alert-id]");
    if (!row) return;
    const alert = latestAlerts.find((item) => String(item.id || "") === row.dataset.alertId);
    if (alert) showAlert(alert);
  });
  loadInitial().finally(connectSocket);
  window.setInterval(refreshMetrics, 15000);
})();
