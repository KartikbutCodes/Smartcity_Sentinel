"use strict";

(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const revealItems = document.querySelectorAll(".reveal");
  const hasIntersectionObserver = "IntersectionObserver" in window;
  const numberObserver = hasIntersectionObserver ? new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      animateNumber(entry.target);
    });
  }, { threshold: 0.25 }) : null;
  let revealObserver = null;
  const pathNodes = new Set();
  let progressFrame = 0;
  let parallaxFrame = 0;
  let drawFrame = 0;
  let lastNarratorText = "";

  if (!reducedMotion && hasIntersectionObserver) {
    document.documentElement.classList.add("has-motion");
    revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08 });
    revealItems.forEach((item) => revealObserver.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-revealed"));
  }

  function formatNumber(value, decimals, suffix) {
    return `${value.toFixed(decimals)}${suffix || ""}`;
  }

  function flash(element) {
    if (reducedMotion) return;
    element.classList.remove("value-flash");
    void element.offsetWidth;
    element.classList.add("value-flash");
    window.setTimeout(() => element.classList.remove("value-flash"), 460);
  }

  function elementIsVisible(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || (rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0);
  }

  function animateNumber(element) {
    if (element.dataset.counted === "true") return;
    const target = Number(element.dataset.countTarget);
    if (!Number.isFinite(target)) return;
    const decimals = Number(element.dataset.countDecimals || 0);
    const suffix = element.dataset.countSuffix || "";
    element.dataset.counted = "true";
    if (reducedMotion) {
      element.textContent = formatNumber(target, decimals, suffix);
      return;
    }
    const started = performance.now();
    const duration = 720;
    function frame(now) {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - ((1 - progress) ** 3);
      element.textContent = formatNumber(target * eased, decimals, suffix);
      if (progress < 1) window.requestAnimationFrame(frame);
      else element.textContent = formatNumber(target, decimals, suffix);
    }
    window.requestAnimationFrame(frame);
  }

  function setNumber(elementOrId, value, decimals = 0, suffix = "") {
    const element = typeof elementOrId === "string" ? document.getElementById(elementOrId) : elementOrId;
    if (!element || !Number.isFinite(Number(value))) return;
    const target = Number(value);
    const previous = element.dataset.countTarget;
    element.dataset.countTarget = String(target);
    element.dataset.countDecimals = String(decimals);
    element.dataset.countSuffix = suffix;
    element.setAttribute("aria-label", formatNumber(target, decimals, suffix));
    if (element.dataset.counted === "true") {
      const next = formatNumber(target, decimals, suffix);
      if (element.textContent !== next) {
        element.textContent = next;
        flash(element);
      }
    } else {
      if (previous !== undefined && previous !== String(target)) element.textContent = "—";
      if (numberObserver && elementIsVisible(element)) {
        animateNumber(element);
        window.setTimeout(() => {
          if (element.dataset.counted !== "true" || element.textContent === "—") {
            element.dataset.counted = "true";
            element.textContent = formatNumber(target, decimals, suffix);
          }
        }, 250);
      } else if (numberObserver) {
        numberObserver.observe(element);
      } else {
        animateNumber(element);
      }
    }
  }

  function setText(elementOrId, value) {
    const element = typeof elementOrId === "string" ? document.getElementById(elementOrId) : elementOrId;
    if (!element) return;
    const next = String(value);
    if (element.textContent !== next) {
      element.textContent = next;
      flash(element);
    }
  }

  async function getJson(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
    return response.json();
  }

  async function refreshApiState() {
    const states = document.querySelectorAll("[data-api-state]");
    if (!states.length) return;
    try {
      const health = await getJson("/health");
      states.forEach((state) => {
        state.classList.toggle("is-live", health.status === "ok");
        state.classList.toggle("is-offline", health.status !== "ok");
        state.querySelector("span").textContent = health.status === "ok" ? "LIVE / LOCAL API" : "OFFLINE";
      });
    } catch {
      states.forEach((state) => {
        state.classList.remove("is-live");
        state.classList.add("is-offline");
        state.querySelector("span").textContent = "OFFLINE";
      });
    }
  }

  async function refreshNarrator() {
    const target = document.getElementById("city-narrator") || document.getElementById("home-narrator");
    if (!target) return;
    try {
      const [alerts, metrics, route] = await Promise.all([
        getJson("/alerts"), getJson("/metrics"), getJson("/route")
      ]);
      const counts = new Map();
      alerts.forEach((alert) => {
        const location = String(alert.location || "Unknown location");
        counts.set(location, (counts.get(location) || 0) + 1);
      });
      const busiest = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
      const locationText = busiest
        ? `${busiest[0]} has the most current alerts`
        : "No alerts are recorded";
      const routeText = Array.isArray(route.path) ? route.path.join(" to ") : "route unavailable";
      const distance = Number.isFinite(route.distance) ? `${route.distance} units` : "distance unavailable";
      const risk = Number.isFinite(metrics.crowd_risk) ? metrics.crowd_risk.toFixed(3) : "unavailable";
      const alertCount = Number.isFinite(metrics.alert_count) ? metrics.alert_count : alerts.length;
      const message = `${locationText} (${alertCount} received). Fastest response route: ${routeText}, ${distance}. Crowd risk: ${risk}.`;
      if (message !== lastNarratorText) {
        target.textContent = message;
        lastNarratorText = message;
      }
      target.classList.remove("home-api-error");
    } catch (error) {
      target.textContent = `Local city summary unavailable: ${error.message}`;
      target.classList.add("home-api-error");
    }
  }

  function updateScrollProgress() {
    progressFrame = 0;
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const progress = scrollable > 0 ? Math.max(0, Math.min(1, window.scrollY / scrollable)) : 0;
    document.querySelectorAll(".scroll-progress span").forEach((bar) => {
      bar.style.transform = `scaleX(${progress})`;
    });
  }

  function updateParallax() {
    parallaxFrame = 0;
    if (reducedMotion) return;
    document.querySelectorAll(".parallax-layer").forEach((layer) => {
      const rect = layer.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      const offset = Math.max(-12, Math.min(12, (rect.top + rect.height / 2 - window.innerHeight / 2) * -0.025));
      layer.style.transform = `translateY(${offset}px)`;
    });
  }

  function registerDrawPaths() {
    document.querySelectorAll("[data-draw-path]").forEach((path) => {
      if (pathNodes.has(path)) return;
      pathNodes.add(path);
      try {
        const length = path.getTotalLength();
        path.style.setProperty("--draw-length", `${length}`);
        path.style.strokeDasharray = `${length}`;
      } catch {
        path.classList.add("is-drawn");
      }
    });
    updateDrawPaths();
  }

  function updateDrawPaths() {
    drawFrame = 0;
    if (reducedMotion) {
      pathNodes.forEach((path) => { path.style.strokeDashoffset = "0"; });
      return;
    }
    pathNodes.forEach((path) => {
      const length = Number.parseFloat(path.style.getPropertyValue("--draw-length"));
      if (!Number.isFinite(length)) return;
      const rect = path.getBoundingClientRect();
      const progress = Math.max(0, Math.min(1, (window.innerHeight - rect.top) / (window.innerHeight + rect.height)));
      path.style.strokeDashoffset = String(length * (1 - progress));
    });
  }

  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest(".panel-help") : null;
    if (!button) return;
    const note = document.getElementById(button.getAttribute("aria-controls"));
    if (!note) return;
    const open = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(open));
    note.hidden = !open;
  });

  window.addEventListener("scroll", () => {
    if (!progressFrame) progressFrame = window.requestAnimationFrame(updateScrollProgress);
    if (!parallaxFrame) parallaxFrame = window.requestAnimationFrame(updateParallax);
    if (!drawFrame) drawFrame = window.requestAnimationFrame(updateDrawPaths);
  }, { passive: true });
  window.addEventListener("resize", registerDrawPaths);
  window.addEventListener("DOMContentLoaded", registerDrawPaths, { once: true });
  window.SentinelUI = {
    getJson,
    setNumber,
    setText,
    flash,
    refreshNarrator,
    refreshDrawPaths: registerDrawPaths,
    reveal(element) {
      if (!element) return;
      if (revealObserver) revealObserver.observe(element);
      else element.classList.add("is-revealed");
    }
  };
  refreshApiState();
  refreshNarrator();
  window.setInterval(refreshApiState, 15000);
  window.setInterval(refreshNarrator, 15000);
  registerDrawPaths();
})();
