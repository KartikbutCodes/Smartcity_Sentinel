"use strict";
(() => {
  const $ = (selector) => document.querySelector(selector);
  async function getJson(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path} returned ${response.status}`);
    return response.json();
  }

  function svg(tag, attributes = {}) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }

  function textNode(text) {
    const node = document.createElement("p");
    node.textContent = text;
    return node;
  }

  function format(value, digits = 2) {
    return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";
  }

  function lineChart(container, values, labels, highest, unit, caption) {
    container.innerHTML = "";
    const width = 240, height = 110;
    const title = document.createElement("h3");
    title.textContent = caption.label;
    const chart = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": caption.label });
    const low = Math.min(...values), high = Math.max(...values), spread = high - low || 1;
    const points = values.map((value, index) => {
      const x = 20 + index * 205 / Math.max(1, values.length - 1);
      const y = 92 - (value - low) / spread * 72;
      return [x, y];
    });
    chart.append(svg("path", {
      d: `M${points.map(([x, y]) => `${x} ${y}`).join(" L")}`,
      fill: "none", stroke: "var(--teal)", "stroke-width": "2"
    }));
    points.forEach(([x, y], index) => {
      const highPoint = highest.includes(index);
      const point = svg("circle", {
        cx: x, cy: y, r: highPoint ? 4 : 2,
        fill: highPoint ? "var(--amber)" : "var(--teal)",
        tabindex: "0", "aria-label": `${labels[index]}, ${format(values[index], 3)} ${unit}`,
        "data-tooltip": `${labels[index]}: ${format(values[index], 3)} ${unit}`
      });
      chart.append(point);
    });
    chart.append(svg("text", { x: 20, y: 106, fill: "var(--muted)", "font-size": "8" }));
    container.append(title, chart);
  }

  function bindTooltips(root) {
    let tooltip = null;
    root.addEventListener("pointerover", (event) => {
      const target = event.target.closest("[data-tooltip]");
      if (!target) return;
      tooltip = document.querySelector(".chart-tooltip");
      if (!tooltip) {
        tooltip = document.createElement("div");
        tooltip.className = "chart-tooltip";
        document.body.append(tooltip);
      }
      tooltip.textContent = target.dataset.tooltip;
      tooltip.hidden = false;
      const rect = target.getBoundingClientRect();
      tooltip.style.left = `${rect.left + window.scrollX}px`;
      tooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;
    });
    root.addEventListener("pointerout", (event) => {
      if (event.target.closest("[data-tooltip]") && tooltip) tooltip.hidden = true;
    });
    root.addEventListener("focusin", (event) => {
      const target = event.target.closest("[data-tooltip]");
      if (!target) return;
      tooltip = tooltip || document.createElement("div");
      tooltip.className = "chart-tooltip";
      document.body.append(tooltip);
      tooltip.textContent = target.dataset.tooltip;
      tooltip.hidden = false;
    });
    root.addEventListener("focusout", () => { if (tooltip) tooltip.hidden = true; });
  }

  async function loadSensors() {
    try {
      const data = await getJson("/examples/sensors");
      const fields = [
        ["power_kw", "Power", "kW", "Power stayed close to the sample"],
        ["water_pressure_kpa", "Water pressure", "kPa", "Water pressure dipped once"],
        ["bridge_vibration", "Bridge vibration", "m/s²", "Bridge vibration rose once"],
        ["aqi", "Air quality", "AQI", "Air quality reached a high sample"],
        ["noise_db", "Noise", "dB", "Noise stayed within the sample"],
        ["flood_level_m", "Flood level", "m", "Flood level crossed the limit"]
      ];
      const root = $("#sensor-charts");
      fields.forEach(([field, label, unit, caption]) => {
        const card = document.createElement("article");
        card.className = "sensor-chart";
        root.append(card);
        lineChart(card, data.rows.map((row) => row[field]), data.rows.map((row) => row.timestamp), data.highest_indexes, unit, { label: `${label}: ${caption}` });
      });
      bindTooltips(root);

      const latest = data.latest;
      $("#latest-reading").innerHTML = [
        ["Power", `${format(latest.power_kw, 2)} kW`],
        ["Water pressure", `${format(latest.water_pressure_kpa, 2)} kPa`],
        ["Bridge vibration", `${format(latest.bridge_vibration, 3)} m/s²`],
        ["Air quality", `${format(latest.aqi, 1)} AQI`],
        ["Noise", `${format(latest.noise_db, 1)} dB`],
        ["Flood level", `${format(latest.flood_level_m, 3)} m`]
      ].map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
      const alerts = data.threshold_alerts;
      $("#threshold-alerts").textContent = alerts.length
        ? alerts.map((alert) => `${alert.kind.replaceAll("_", " ")} ${format(alert.value, 3)} is above the ${format(alert.threshold, 3)} limit`).join(". ")
        : "No configured threshold alert is active.";
      const index = data.highest_indexes[0];
      const row = data.rows[index];
      $("#sensor-raw-strip").textContent =
        `Row ${index}: flood level ${format(row.flood_level_m, 3)} m, unusual score ${format(row.unusual_score, 6)}. ${alerts.length ? "The row can become a flood alert." : "The row did not cross a configured limit."}`;
      return data;
    } catch (error) {
      $("#sensor-charts").textContent = "The sensor example is unavailable.";
      $("#threshold-alerts").textContent = error.message;
    }
  }

  function barChart(svgElement, values, labels, color = "var(--teal)") {
    svgElement.replaceChildren();
    const width = 420, height = 160, left = 35, bottom = 132;
    const max = Math.max(1, ...values);
    svgElement.append(svg("line", { x1: left, y1: bottom, x2: 395, y2: bottom, stroke: "var(--hairline)" }));
    values.forEach((value, index) => {
      const step = 360 / Math.max(1, values.length);
      const x = left + index * step + 8;
      const barHeight = value / max * 95;
      const rect = svg("rect", { x, y: bottom - barHeight, width: Math.max(10, step - 16), height: barHeight, fill: color, tabindex: "0", "aria-label": `${labels[index]}: ${value}` });
      const title = svg("title");
      title.textContent = `${labels[index]}: ${value}`;
      rect.append(title);
      svgElement.append(rect);
      const label = svg("text", { x: x + 5, y: 150, fill: "var(--muted)", "font-size": "8" });
      label.textContent = labels[index];
      svgElement.append(label);
    });
  }

  async function loadTraffic() {
    let data;
    try { data = await getJson("/examples/traffic-camera"); }
    catch (error) { $("#traffic-counts").textContent = error.message; return null; }

    let frameIndex = 0;
    let playing = false;
    let timer = null;
    let speed = 1;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = $("#traffic-objects");

    function drawFrame(index) {
      frameIndex = Math.max(0, Math.min(data.frames.length - 1, index));
      scene.replaceChildren();
      const frame = data.frames[frameIndex];
      const detections = frame.detections
        .filter((detection) => detection.label !== "person")
        .concat(frame.detections.filter((detection) => detection.label === "person"));
      detections.forEach((detection) => {
        const [x1, y1, x2, y2] = detection.box;
        const x = x1 * 720, y = y1 * 360, width = (x2 - x1) * 720, height = (y2 - y1) * 360;
        const group = svg("g", { "aria-label": `${detection.label} ${detection.track_id}` });
        if ($("#traffic-boxes").checked) {
          group.append(svg("rect", { x, y, width, height, fill: "none", stroke: "var(--amber)", "stroke-width": "2" }));
          const tag = svg("text", { x: x + 2, y: y - 4, fill: "var(--ink)", "font-size": "10", "font-family": "var(--sans)" });
          tag.textContent = `${detection.label} ${detection.track_id}`;
          group.append(tag);
        }
        if (detection.label === "person") {
          group.append(svg("circle", { cx: x + width / 2, cy: y + height / 2 - 8, r: 7, fill: "var(--teal)" }));
        } else if (detection.label === "bike") {
          group.append(svg("circle", { cx: x + width * .25, cy: y + height * .8, r: 9, fill: "none", stroke: "var(--ink)", "stroke-width": "3" }));
          group.append(svg("circle", { cx: x + width * .75, cy: y + height * .8, r: 9, fill: "none", stroke: "var(--ink)", "stroke-width": "3" }));
        } else {
          group.append(svg("rect", { x: x + 4, y: y + 5, width: Math.max(8, width - 8), height: Math.max(8, height - 10), rx: 5, fill: "var(--teal)", stroke: "var(--ink)", "stroke-width": "2" }));
        }
        scene.append(group);
      });
      $("#traffic-scrub").value = String(frameIndex);
      const counts = frame.metadata.counts;
      $("#traffic-counts").textContent = `Counts: ${Object.entries(counts).map(([key, value]) => `${value} ${key}`).join(", ") || "no detections"}.`;
      const crossings = data.crossings.filter((item) => item.frame <= frameIndex);
      $("#traffic-crossings").textContent = `Crossings: ${crossings.length}.`;
      $("#traffic-speeds").textContent = data.speeds.length
        ? `Speeds: ${data.speeds.map((item) => `${item.track_id} ${format(item.speed_kmh, 1)} km/h`).join(", ")}.`
        : "Speeds: loading.";
      $("#traffic-summary").textContent = `Second ${frame.second}: counts only. No video kept.`;
      $("#store-counts").textContent = `Counts at this frame: ${Object.entries(counts).map(([key, value]) => `${value} ${key}`).join(", ") || "none"}.`;
      $("#store-speeds").textContent = data.speeds.map((item) => `${item.track_id}: ${format(item.speed_kmh, 1)} km/h`).join("; ");
      const crossed = data.crossings.some((item) => item.frame === frameIndex);
      $("#count-line").classList.toggle("is-crossing", crossed);
    }

    function stopTimer() { if (timer) window.clearInterval(timer); timer = null; playing = false; $("#traffic-play").textContent = "Play"; }
    function startTimer() {
      if (reduced) return;
      playing = true;
      $("#traffic-play").textContent = "Pause";
      timer = window.setInterval(() => {
        if (frameIndex >= data.frames.length - 1) stopTimer();
        else drawFrame(frameIndex + 1);
      }, 200 / speed);
    }
    $("#traffic-play").addEventListener("click", () => playing ? stopTimer() : startTimer());
    $("#traffic-scrub").addEventListener("input", (event) => drawFrame(Number(event.target.value)));
    $("#traffic-speed").addEventListener("change", (event) => {
      speed = Number(event.target.value);
      if (playing) { stopTimer(); startTimer(); }
    });
    $("#traffic-boxes").addEventListener("change", () => drawFrame(frameIndex));
    $("#camera-view-toggle").addEventListener("change", (event) => {
      $("#traffic-scene").hidden = event.target.checked;
      $(".camera-controls").hidden = event.target.checked;
      $(".records-log").hidden = event.target.checked;
      $("#store-card").hidden = !event.target.checked;
    });
    barChart($("#vehicle-bin-chart"), data.vehicles_per_5_seconds, ["0-5","5-10","10-15","15-20","20-25","25-30"], "var(--teal)");
    barChart($("#speed-chart"), data.speeds.map((item) => item.speed_kmh), data.speeds.map((item) => String(item.track_id)), "var(--amber)");
    const ratio = data.edge_cloud.bandwidth_reduction_ratio * 100;
    $("#weight-saving").textContent = `${format(ratio, 2)}%`;
    $("#weight-detail").textContent =
      `Raw video: ${Math.round(data.edge_cloud.cloud_uplink_bytes).toLocaleString()} bytes. Summaries: ${Math.round(data.edge_cloud.edge_uplink_bytes).toLocaleString()} bytes.`;
    drawFrame(0);
    return data;
  }

  async function loadPlate() {
    let data;
    try { data = await getJson("/examples/plate-camera"); }
    catch (error) { $("#plate-table tbody").textContent = error.message; return null; }
    const crops = $("#plate-crops");
    crops.replaceChildren();
    data.reads.forEach((read) => {
      const card = document.createElement("div");
      card.className = "plate-crop";
      const plateSvg = svg("svg", { viewBox: "0 0 100 42", "aria-label": `${read.plate_text}, random, not a real vehicle` });
      plateSvg.append(svg("rect", { x: 4, y: 5, width: 92, height: 32, rx: 3, fill: "#F1C94B", stroke: "var(--ink)", "stroke-width": "2" }));
      const label = svg("text", { x: 50, y: 26, "text-anchor": "middle", fill: "var(--ink)", "font-size": "10", "font-family": "var(--mono)" });
      label.textContent = read.plate_text;
      plateSvg.append(label);
      card.append(plateSvg);
      const small = document.createElement("small");
      small.textContent = "random, not a real vehicle";
      card.append(small);
      crops.append(card);
    });

    const tbody = $("#plate-table tbody");
    tbody.replaceChildren();
    data.reads.forEach((read) => {
      const row = document.createElement("tr");
      row.innerHTML =
        `<td>${read.time.slice(11, 16)}</td><td>${read.plate_text}</td><td>${format(read.confidence, 3)}</td>` +
        `<td><span class="${read.valid ? "valid-badge" : "invalid-badge"}">${read.valid ? "Valid" : "Not valid"}</span></td>`;
      tbody.append(row);
      if (!read.valid) row.title = read.misread_explanation;
    });
    barChart($("#hour-chart"), data.reads_per_hour.map((item) => item.count), data.reads_per_hour.map((item) => item.hour), "var(--teal)");

    const select = $("#read-select");
    data.reads.forEach((read, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = read.plate_text;
      select.append(option);
    });
    function showRead(index) {
      const read = data.reads[index];
      $("#before-record").textContent = JSON.stringify(read.before, null, 2);
      $("#after-record").textContent = JSON.stringify(read.after, null, 2);
      const beforeMetadata = read.before.metadata || {};
      const afterMetadata = read.after.metadata || {};
      const removed = Object.keys(beforeMetadata).filter((key) => !(key in afterMetadata));
      $("#privacy-change").textContent = removed.length
        ? `The output removed these metadata fields: ${removed.join(", ")}.`
        : "The output kept the metadata fields.";
    }
    select.addEventListener("change", () => showRead(Number(select.value)));
    showRead(0);
    return data;
  }

  async function loadJourney(sensorData, trafficData, plateData) {
    if (sensorData) {
      const row = sensorData.rows[sensorData.highest_indexes[0]];
      $("#journey-camera").textContent = `Flood level ${format(row.flood_level_m, 3)} m.`;
      $("#journey-check").textContent = `Unusual score ${format(row.unusual_score, 6)}.`;
      $("#journey-alert").textContent = sensorData.threshold_alerts.length ? "A flood alert is ready." : "No threshold alert is ready.";
    }
    if (trafficData) {
      $("#journey-summary").textContent = `${trafficData.frames[0].metadata.counts.car || 0} cars in one sample.`;
      $("#journey-dashboard").textContent = "Counts appear in the live panel.";
    }
    if (plateData) {
      $("#journey-privacy").textContent = `Read ${plateData.reads[0].id} uses the real minimizer output.`;
    }
  }

  function setupJourney() {
    const steps = document.querySelectorAll("[data-step]");
    if (!window.IntersectionObserver) {
      steps.forEach((step) => step.classList.add("is-visible"));
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      steps.forEach((step) => step.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add("is-visible"); });
    }, { threshold: 0.35 });
    steps.forEach((step) => observer.observe(step));
  }

  async function init() {
    const sensorData = await loadSensors();
    const trafficData = await loadTraffic();
    const plateData = await loadPlate();
    await loadJourney(sensorData, trafficData, plateData);
    setupJourney();
  }
  init();
})();
