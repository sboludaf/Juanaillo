"use strict";

(() => {
  const buttons = [...document.querySelectorAll("[data-direction]")];
  const connection = document.querySelector(".connection");
  const connectionLabel = document.getElementById("connection-label");
  const motionStatus = document.getElementById("motion-status");
  const directionLabels = { forward: "Avance", reverse: "Retroceso", left: "Izquierda", right: "Derecha" };
  const fragmentToken = new URLSearchParams(location.hash.slice(1)).get("token");
  let token = fragmentToken;
  // Session-only access survives refresh; motion state is never persisted.
  // Blocked storage still permits a link token to work in memory for this load.
  try {
    if (fragmentToken) sessionStorage.setItem("juanaillo-control-token", fragmentToken);
    else token = sessionStorage.getItem("juanaillo-control-token");
  } catch { /* Keep the in-memory token when browser storage is unavailable. */ }
  if (fragmentToken) history.replaceState(null, "", location.pathname + location.search);

  let socket = null;
  let authenticated = false;
  let ready = false;
  let sequence = 0;
  let owner = null;
  let heartbeat = null;
  let lastStatusAt = 0;
  let reconnect = null;
  let leaving = false;

  function send(type, fields = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN || !authenticated) return false;
    try {
      socket.send(JSON.stringify({ type, seq: ++sequence, ...fields }));
      return true;
    } catch {
      authenticated = false;
      disconnect("Conexión interrumpida");
      return false;
    }
  }

  function renderControls() {
    for (const button of buttons) {
      // Keep a physically held control listening for its release after LIMIT.
      button.disabled = !ready && !(owner?.awaitingRelease && owner.direction === button.dataset.direction);
      button.setAttribute("aria-pressed", String(owner?.direction === button.dataset.direction));
    }
  }

  function setConnection(label, state) {
    connectionLabel.textContent = label;
    connection.dataset.state = state;
  }

  function stop() {
    const previous = owner;
    owner = null;
    clearInterval(heartbeat);
    heartbeat = null;
    // STOP is idempotent; also send it for blur/hidden with no current owner.
    send("stop");
    if (previous && ready) motionStatus.textContent = "Parando…";
    renderControls();
  }

  function disconnect(message) {
    stop();
    ready = false;
    authenticated = false;
    setConnection("Sin conexión", "offline");
    motionStatus.textContent = message;
    renderControls();
  }

  function hold(direction, kind, id) {
    if (owner || !ready || !authenticated || document.hidden) return;
    owner = { direction, kind, id };
    if (!send("hold", { direction })) {
      stop();
      return;
    }
    motionStatus.textContent = `${directionLabels[direction]} · suelta para parar`;
    renderControls();
    heartbeat = setInterval(() => {
      if (!owner || !ready || document.hidden) {
        stop();
        return;
      }
      if (!send("heartbeat")) stop();
    }, 50);
  }

  function applyStatus(status) {
    lastStatusAt = performance.now();
    // Only an explicit fresh backend-ready status may enable motion.
    ready = authenticated && status.controller === true && status.connected === true &&
      status.ready === true && !status.release_required && !status.error;
    if (status.release_required || status.state === "limit") {
      clearInterval(heartbeat);
      heartbeat = null;
      if (owner) owner.awaitingRelease = true;
    } else if (!ready && owner) {
      stop();
    }
    const simulated = status.simulated === true;
    if (ready) {
      setConnection(simulated ? "Simulador conectado" : "H60 conectada", "ready");
      if (!owner) motionStatus.textContent = status.moving === true ? "Parando…" : "Listo · motores parados";
    } else {
      const device = simulated ? "Simulador" : "H60";
      setConnection(status.connected === true ? `${device} no disponible` : `${device} desconectada`, "waiting");
      motionStatus.textContent = status.error || (status.state === "limit" || status.release_required
        ? "Límite alcanzado · suelta y vuelve a pulsar"
        : "Esperando al controlador · movimiento deshabilitado");
    }
    renderControls();
  }

  function connect() {
    if (leaving) return;
    if (!token) {
      setConnection("Acceso sin clave", "waiting");
      motionStatus.textContent = "Abre el enlace local que muestra el servidor.";
      renderControls();
      return;
    }
    setConnection("Conectando…", "waiting");
    const candidate = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`);
    socket = candidate;
    sequence = 0;
    candidate.addEventListener("open", () => {
      if (socket === candidate) candidate.send(JSON.stringify({ type: "hello", token }));
    });
    candidate.addEventListener("message", (event) => {
      if (socket !== candidate) return;
      let data;
      try {
        data = JSON.parse(event.data);
        if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Invalid message");
      } catch {
        disconnect("Respuesta no válida · movimiento deshabilitado");
        candidate.close();
        return;
      }
      if (data.type === "hello") {
        authenticated = data.ok === true && data.controller === true;
        if (!authenticated) {
          ready = false;
          setConnection("Sin acceso de control", "error");
          motionStatus.textContent = "El enlace no permite controlar esta sesión.";
          renderControls();
        }
      } else if (data.type === "status") {
        applyStatus(data);
      } else if (data.type === "error") {
        stop();
        ready = false;
        setConnection("Control detenido", "error");
        motionStatus.textContent = data.message || "Error del controlador · movimiento deshabilitado";
        renderControls();
      }
    });
    candidate.addEventListener("close", () => {
      if (socket !== candidate) return;
      disconnect("Conexión cerrada · movimiento deshabilitado");
      socket = null;
      if (!leaving) reconnect = setTimeout(connect, 1500);
    });
    candidate.addEventListener("error", () => {
      if (socket === candidate) disconnect("No se puede conectar con el servidor local.");
    });
  }

  for (const button of buttons) {
    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      if (owner || !ready) return;
      hold(button.dataset.direction, "pointer", event.pointerId);
      if (owner?.kind === "pointer" && owner.id === event.pointerId) {
        try { button.setPointerCapture(event.pointerId); } catch { stop(); }
      }
    });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture", "pointerleave"]) {
      button.addEventListener(type, (event) => {
        if (owner?.kind === "pointer" && owner.id === event.pointerId) stop();
      });
    }
    button.addEventListener("contextmenu", (event) => event.preventDefault());
    button.addEventListener("dragstart", (event) => event.preventDefault());
    button.addEventListener("blur", () => {
      if (owner?.kind === "keyboard" && ["Space", "Enter"].includes(owner.id) &&
          owner.direction === button.dataset.direction) stop();
    });
  }

  function keyDirection(event) {
    const directions = {
      ArrowUp: "forward", KeyW: "forward", ArrowDown: "reverse", KeyS: "reverse",
      ArrowLeft: "left", KeyA: "left", ArrowRight: "right", KeyD: "right",
    };
    if (directions[event.code]) return directions[event.code];
    if ((event.code === "Space" || event.code === "Enter") && buttons.includes(document.activeElement)) return document.activeElement.dataset.direction;
    return null;
  }
  window.addEventListener("keydown", (event) => {
    // Browser shortcuts such as Ctrl+A/Ctrl+S must never start a motor command.
    if (event.ctrlKey || event.metaKey || event.altKey) {
      if (owner) stop();
      return;
    }
    const direction = keyDirection(event);
    if (!direction) return;
    event.preventDefault();
    if (!event.repeat) hold(direction, "keyboard", event.code);
  });
  window.addEventListener("keyup", (event) => {
    if (owner?.kind === "keyboard" && owner.id === event.code) {
      event.preventDefault();
      stop();
    }
  });
  window.addEventListener("blur", stop);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
  window.addEventListener("beforeunload", stop);
  window.addEventListener("pagehide", () => {
    leaving = true;
    clearTimeout(reconnect);
    stop();
    socket?.close();
  });
  // A frozen/stale status stream cannot keep browser commands alive.
  setInterval(() => {
    if (ready && performance.now() - lastStatusAt > 1000) {
      stop();
      ready = false;
      setConnection("Sin respuesta", "error");
      motionStatus.textContent = "Estado desactualizado · movimiento deshabilitado";
      renderControls();
    }
  }, 100);

  connect();
})();
