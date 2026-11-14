"use strict";

(() => {
  const ui = window.SentinelUI;
  const positions = {
    Central: [215, 220],
    North: [410, 120],
    River: [410, 320],
    Market: [610, 220]
  };
  const locations = {
    "central junction": "Central",
    "north bridge": "North",
    "river ward": "River",
    "market square": "Market"
  };
  const storyStages = [
    ["sensor", "01 / SENSOR", "A generated reading enters the local path."],
    ["edge", "02 / EDGE", "The edge example keeps metadata, not frames."],
    ["queue", "03 / QUEUE", "The demo queue is in-process and temporary."],
    ["checks", "04 / CHECKS", "A fixed score and compact scorers inspect the sample."],
    ["privacy", "05 / PRIVACY", "The minimizer applies its explicit field allowlist."],
    ["api", "06 / API", "The local API returns the state to this page."],
    ["you", "07 / YOU", "The browser is the last step in this local path."]
  ];
  let storyData = {};
  let routeSignature = "";

  function svg(name, attributes = {}) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function formatBytes(bytes) {
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(2)} MB`;
    if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(2)} KB`;
    return `${bytes} B`;
  }

  function severityLevel(alert) {
    const value = Number(alert.severity);
    if (!Number.isFinite(value)) return "low";
    if (value >= 0.75) return "high";
    if (value >= 0.45) return "medium";
    return "low";
  }

  async function postJson(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `${path} failed`);
    return result;
  }

  function renderHomeRoute(route) {
    const layer = document.getElementById("home-route-layer");
    layer.replaceChildren();
    if (!Array.isArray(route.path) || route.path.length < 2) return;
    const points = route.path.map((name) => positions[name]).filter(Boolean);
    if (points.length < 2) return;
    const line = svg("polyline", {
      points: points.map(([x, y]) => `${x},${y}`).join(" "),
      class: "hero-route draw-on-scroll",
      "data-draw-path": ""
    });
    layer.append(line);
    ui.refreshDrawPaths();
  }

  function paintHomeNodes(alerts) {
    document.querySelectorAll(".home-city-node").forEach((group) => {
      const location = group.dataset.location.toLowerCase();
      const nodeName = locations[location];
      const latest = alerts
        .filter((alert) => locations[String(alert.location || "").toLowerCase()] === nodeName)
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0];
      const level = latest ? severityLevel(latest) : "low";
      const marker = group.querySelector(".hero-node");
      const pulse = group.querySelector(".hero-node-pulse");
      marker.setAttribute("class", `hero-node severity-${level}`);
      pulse.setAttribute("class", `hero-node-pulse severity-${level}`);
      group.querySelector(".hero-severity-label").textContent = latest
        ? level === "medium" ? "MED" : level.toUpperCase()
        : "NO ALERT";
      const title = svg("title");
      title.textContent = latest ? `${level.toUpperCase()} alert at ${group.dataset.location}` : `No alert at ${group.dataset.location}`;
      const prior = group.querySelector("title");
      if (prior) prior.remove();
      group.prepend(title);
    });
  }

  function displayMetricStrip(metrics, route) {
    ui.setNumber("home-crowd", metrics.crowd_risk, 3);
    ui.setNumber("home-alerts", metrics.alert_count, 0);
    ui.setNumber("home-route-distance", route.distance, 1, " units");
    const audit = document.getElementById("home-audit");
    const valid = metrics.audit_chain_valid === true;
    audit.textContent = valid ? "VALID" : metrics.audit_chain_valid === false ? "INVALID" : "UNAVAILABLE";
    audit.classList.toggle("status-attention", metrics.audit_chain_valid === undefined);
    audit.classList.toggle("status-invalid", metrics.audit_chain_valid === false);
  }

  function updateStorySnippet(stage) {
    const value = storyData[stage];
    const output = document.getElementById("signal-snippet");
    output.textContent = value === undefined ? "Waiting for the local API…" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
    const step = storyStages.find((item) => item[0] === stage);
    if (!step) return;
    document.getElementById("story-stage-label").textContent = step[1];
    document.getElementById("story-stage-caption").textContent = step[2];
    document.querySelectorAll("[data-scene]").forEach((scene) => {
      scene.classList.toggle("is-active", scene.dataset.scene === stage);
    });
    const index = storyStages.findIndex((item) => item[0] === stage);
    document.getElementById("story-signal-dot").setAttribute("cx", String([82, 141, 219, 291, 365, 434, 474][index]));
  }

  function setupStory() {
    const steps = document.querySelectorAll(".story-step");
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      const active = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!active) return;
      steps.forEach((step) => step.classList.toggle("is-active", step === active.target));
      updateStorySnippet(active.target.dataset.stage);
    }, { rootMargin: "-30% 0px -35% 0px", threshold: [0.1, 0.3, 0.6] });
    steps.forEach((step) => observer.observe(step));
  }

  function renderRouteMini(route, city) {
    const canvas = document.getElementById("cap-route-map");
    const coords = { Central: [42, 64], North: [112, 22], River: [112, 106], Market: [238, 64] };
    const graph = city.graph || city;
    Object.entries(graph).forEach(([from, edges]) => {
      Object.keys(edges).forEach((to) => {
        if (from.localeCompare(to) >= 0 || !coords[from] || !coords[to]) return;
        canvas.append(svg("line", { x1: coords[from][0], y1: coords[from][1], x2: coords[to][0], y2: coords[to][1], class: "graphic-stroke" }));
      });
    });
    const routePoints = route.path.map((name) => coords[name]).filter(Boolean);
    if (routePoints.length > 1) {
      canvas.append(svg("polyline", {
        points: routePoints.map(([x, y]) => `${x},${y}`).join(" "),
        class: "route-line draw-on-scroll",
        "data-draw-path": ""
      }));
    }
    Object.entries(coords).forEach(([name, [x, y]]) => {
      canvas.append(svg("circle", { cx: x, cy: y, r: 5, class: "graphic-teal" }));
      const label = svg("text", { x, y: y + 17, fill: "var(--ink)", "font-size": 8, "font-family": "var(--sans)", "text-anchor": "middle" });
      label.textContent = name.toUpperCase();
      canvas.append(label);
    });
    ui.setText("cap-route-value", `${route.path.join(" → ")} / ${route.distance} units`);
  }

  function renderCrowdMini(result) {
    const grid = document.getElementById("cap-crowd-grid");
    const max = Math.max(1, ...result.grid.flat());
    const palette = { low: "#b7cbd4", medium: "#d9822b", high: "#c8442f" };
    grid.replaceChildren();
    result.heatmap.forEach((row, y) => row.forEach((value, x) => {
      const level = value >= 0.8 ? "high" : value >= 0.45 ? "medium" : "low";
      grid.append(svg("rect", {
        x, y, width: 1, height: 1,
        fill: palette[level],
        stroke: "#ffffff",
        "stroke-width": 0.08,
        "aria-label": `${result.grid[y][x]} generated points`
      }));
    }));
    const risk = Number(result.crowd_risk);
    ui.setText("cap-crowd-value", `RISK ${Number.isFinite(risk) ? risk.toFixed(3) : "UNAVAILABLE"} · PEAK ${max}`);
  }

  function renderAuditMini(result) {
    const svgRoot = document.getElementById("cap-audit-chain");
    const blocks = result.blocks || [];
    blocks.slice(0, 5).forEach((block, index) => {
      const x = 5 + index * 71;
      if (index) svgRoot.append(svg("line", { x1: x - 13, y1: 61, x2: x - 3, y2: 61, class: "graphic-stroke draw-on-scroll", "data-draw-path": "" }));
      const group = svg("g");
      group.append(svg("rect", { x, y: 30, width: 60, height: 58, rx: 5, class: "graphic-warm" }));
      const title = svg("text", { x: x + 30, y: 50, fill: "var(--ink)", "font-size": 8, "font-family": "var(--mono)", "text-anchor": "middle" });
      title.textContent = `BLOCK ${block.number}`;
      const hash = svg("text", { x: x + 30, y: 68, fill: "var(--muted)", "font-size": 7, "font-family": "var(--mono)", "text-anchor": "middle" });
      hash.textContent = String(block.hash || "").slice(0, 8);
      group.append(title, hash);
      svgRoot.append(group);
    });
    ui.setText("cap-audit-value", result.valid_before_tamper ? "VALID BEFORE EDIT / INVALID AFTER" : "CHAIN CHECK UNAVAILABLE");
    ui.refreshDrawPaths();
  }

  async function loadStory(alerts, metrics, route) {
    const alert = alerts[0] || {};
    const severity = Number(alert.severity);
    const score = await postJson("/tools/priority", {
      severity: Number.isFinite(severity) ? severity : 0,
      impact: 0.5,
      confidence: 1
    });
    const eventForMinimization = {
      ...alert,
      metadata: { ...(alert.metadata || {}), plate: "EXAMPLE-PLATE" }
    };
    const minimized = await postJson("/tools/minimize", eventForMinimization);
    const [health, edgeResult] = await Promise.all([
      ui.getJson("/health"),
      postJson("/tools/edge", { detections: [{ label: "vehicle", confidence: 0.9 }], confidence_threshold: 0.5 })
    ]);
    storyData = {
      sensor: alert,
      edge: edgeResult,
      queue: { queued_demo_alerts: metrics.queued_demo_alerts, alert_count: metrics.alert_count },
      checks: { priority: score, anomaly_scores: metrics.anomaly_scores },
      privacy: minimized,
      api: { health, route },
      you: "This record has reached your browser on the local machine."
    };
    const count = metrics.queued_demo_alerts;
    document.getElementById("queue-story-text").textContent = Number.isFinite(count)
      ? `${count} generated alert records passed through the in-process demo queue. This is a startup snapshot.`
      : "The API did not return a queue snapshot for this run.";
    document.getElementById("priority-story-text").textContent =
      `The selected alert scored ${Number(score.score).toFixed(4)} and received a ${String(score.priority).toUpperCase()} label under the fixed rule.`;
    updateStorySnippet("sensor");
  }

  async function loadPageData() {
    try {
      const [alerts, metrics, route, city] = await Promise.all([
        ui.getJson("/alerts"), ui.getJson("/metrics"), ui.getJson("/route"), ui.getJson("/city")
      ]);
      displayMetricStrip(metrics, route);
      renderHomeRoute(route);
      routeSignature = route.path.join("|");
      paintHomeNodes(alerts);
      renderRouteMini(route, city);
      const [crowd, audit] = await Promise.all([ui.getJson("/tools/crowd"), ui.getJson("/tools/audit-chain")]);
      renderCrowdMini(crowd);
      renderAuditMini(audit);
      const scores = metrics.anomaly_scores || {};
      const isolation = Number(scores.isolation_forest);
      const reconstruction = Number(scores.autoencoder_reconstruction_error);
      ui.setText("cap-anomaly-value", `ISOLATION ${Number.isFinite(isolation) ? isolation.toFixed(3) : "—"} · ERROR ${Number.isFinite(reconstruction) ? reconstruction.toFixed(3) : "—"}`);
      const minimized = await postJson("/tools/minimize", { ...(alerts[0] || {}), metadata: { ...((alerts[0] || {}).metadata || {}), plate: "EXAMPLE-PLATE" } });
      document.getElementById("cap-privacy-before").textContent = JSON.stringify(minimized.before, null, 2);
      document.getElementById("cap-privacy-after").textContent = JSON.stringify(minimized.after, null, 2);
      const bytes = metrics.edge_cloud || {};
      document.getElementById("camera-edge-bytes").textContent = formatBytes(bytes.edge_uplink_bytes);
      document.getElementById("camera-cloud-bytes").textContent = formatBytes(bytes.cloud_uplink_bytes);
      document.getElementById("camera-reduction").textContent =
        `The API's illustrative estimate is ${(bytes.bandwidth_reduction_ratio * 100).toFixed(2)}% less uplink for edge metadata.`;
      await loadStory(alerts, metrics, route);
      ui.refreshDrawPaths();
    } catch (error) {
      document.querySelectorAll(".home-live-cell strong").forEach((value) => {
        if (value.textContent === "—") value.textContent = "OFFLINE";
      });
      document.getElementById("signal-snippet").textContent = `Local API response unavailable: ${error.message}`;
      document.getElementById("cap-route-value").textContent = "API unavailable";
      document.getElementById("cap-crowd-value").textContent = "API unavailable";
      document.getElementById("cap-anomaly-value").textContent = "API unavailable";
      document.getElementById("cap-audit-value").textContent = "API unavailable";
    }
  }

  async function refreshLiveValues() {
    try {
      const [alerts, metrics, route] = await Promise.all([
        ui.getJson("/alerts"), ui.getJson("/metrics"), ui.getJson("/route")
      ]);
      displayMetricStrip(metrics, route);
      paintHomeNodes(alerts);
      const nextRoute = route.path.join("|");
      if (routeSignature !== nextRoute) {
        routeSignature = nextRoute;
        renderHomeRoute(route);
      }
    } catch (error) {
      const narrator = document.getElementById("home-narrator");
      narrator.textContent = `Local city summary unavailable: ${error.message}`;
      narrator.classList.add("home-api-error");
    }
  }

  setupStory();
  loadPageData();
  window.setInterval(refreshLiveValues, 15000);
})();
