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
  const heldInputs = new Map();
  const releaseMessage = "Suelta todos los controles para continuar";
  let releaseLatch = false;
  let releaseHint = releaseMessage;
  let stopPending = 0;
  let stopAccepted = false;
  let heartbeat = null;
  let lastStatusAt = 0;
  let reconnect = null;
  let leaving = false;

  function send(type, fields = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN || !authenticated) return false;
    try {
      socket.send(JSON.stringify({ type, seq: ++sequence, ...fields }));
      return sequence;
    } catch {
      authenticated = false;
      disconnect("Conexión interrumpida");
      return false;
    }
  }

  function renderControls() {
    for (const button of buttons) {
      // All held pointers must still deliver their release while motion is blocked.
      button.disabled = !ready && heldInputs.size === 0;
      button.setAttribute("aria-disabled", String(!ready || releaseLatch));
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
    const stopSeq = send("stop");
    if (stopSeq) {
      stopPending = stopSeq;
      stopAccepted = false;
      ready = false;
    }
    if (previous && !releaseLatch) motionStatus.textContent = "Parando…";
    renderControls();
  }

  function disconnect(message) {
    if (heldInputs.size) releaseLatch = true;
    stop();
    ready = false;
    authenticated = false;
    stopPending = 0;
    stopAccepted = false;
    setConnection("Sin conexión", "offline");
    motionStatus.textContent = message;
    renderControls();
  }

  function hold(direction, kind, id, token) {
    if (owner || releaseLatch || !ready || !authenticated || document.hidden) return;
    owner = { direction, kind, id, token };
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

  function blockUntilReleased() {
    releaseLatch = true;
    releaseHint = releaseMessage;
    stop();
    motionStatus.textContent = releaseHint;
  }

  function beginInput(token, direction, kind, id) {
    const existing = heldInputs.get(token);
    if (existing) {
      if (existing.direction !== direction) blockUntilReleased();
      return;
    }
    heldInputs.set(token, { direction, kind, id });
    if (releaseLatch || heldInputs.size > 1) {
      blockUntilReleased();
    } else if (!ready || !authenticated || document.hidden) {
      releaseLatch = true;
      releaseHint = releaseMessage;
      renderControls();
    } else {
      hold(direction, kind, id, token);
    }
  }

  function endInput(token) {
    if (!heldInputs.has(token)) return;
    const wasOwner = owner?.token === token;
    heldInputs.delete(token);
    if (heldInputs.size === 0) {
      const needsRelease = releaseLatch;
      releaseLatch = false;
      if (wasOwner || needsRelease) stop();
      else renderControls();
    } else if (wasOwner) {
      blockUntilReleased();
    } else {
      renderControls();
      if (releaseLatch) motionStatus.textContent = releaseHint;
    }
  }

  function cancelAllInputs() {
    heldInputs.clear();
    releaseLatch = false;
    stop();
  }

  function applyStatus(status) {
    lastStatusAt = performance.now();
    // Only an explicit fresh backend-ready status may enable motion.
    const deviceReady = authenticated && status.controller === true && status.connected === true &&
      status.ready === true && !status.release_required && !status.error;
    // WS ACK accepts STOP; this later idle snapshot confirms the device replied.
    if (stopPending && stopAccepted && deviceReady && status.stop_pending === false &&
        status.state === "idle" && status.held === false && status.moving === false) {
      stopPending = 0;
      stopAccepted = false;
    }
    ready = deviceReady && !stopPending;
    if (status.release_required || status.state === "limit") {
      clearInterval(heartbeat);
      heartbeat = null;
      owner = null;
      releaseLatch = true;
      releaseHint = status.stop_reason === "input_conflict" ? releaseMessage
        : status.state === "limit" ? "Límite alcanzado · suelta y vuelve a pulsar" : releaseMessage;
    } else if (!ready && owner) {
      releaseLatch = heldInputs.size > 0;
      stop();
    }
    if (deviceReady && !status.release_required && heldInputs.size === 0) releaseLatch = false;
    const simulated = status.simulated === true;
    if (ready) {
      setConnection(simulated ? "Simulador conectado" : "H60 conectada", "ready");
      if (releaseLatch) motionStatus.textContent = releaseHint;
      else if (!owner) motionStatus.textContent = status.moving === true ? "Parando…" : "Listo · motores parados";
    } else {
      const device = simulated ? "Simulador" : "H60";
      setConnection(status.connected === true ? `${device} no disponible` : `${device} desconectada`, "waiting");
      motionStatus.textContent = status.error || (releaseLatch
        ? releaseHint
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
      } else if (data.type === "ack" && data.action === "stop" && data.seq === stopPending) {
        stopAccepted = true;
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
      beginInput(`pointer:${event.pointerId}`, button.dataset.direction, "pointer", event.pointerId);
      try { button.setPointerCapture(event.pointerId); } catch { blockUntilReleased(); }
    });
    for (const type of ["lostpointercapture", "pointerleave"]) {
      button.addEventListener(type, (event) => {
        // Capture loss/leave is not a physical release; global up/cancel ends it.
        if (heldInputs.has(`pointer:${event.pointerId}`)) blockUntilReleased();
      });
    }
    button.addEventListener("contextmenu", (event) => event.preventDefault());
    button.addEventListener("dragstart", (event) => event.preventDefault());
    button.addEventListener("blur", () => {
      if (owner?.kind === "keyboard" && ["Space", "Enter"].includes(owner.id) &&
          owner.direction === button.dataset.direction) blockUntilReleased();
    });
  }
  for (const type of ["pointerup", "pointercancel"]) {
    window.addEventListener(type, (event) => endInput(`pointer:${event.pointerId}`), true);
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
    const direction = keyDirection(event);
    const token = `key:${event.code}`;
    // Browser shortcuts such as Ctrl+A/Ctrl+S must never start a motor command.
    if (event.ctrlKey || event.metaKey || event.altKey) {
      if (direction && !event.repeat) heldInputs.set(token, { direction, kind: "keyboard", id: event.code });
      if (owner) blockUntilReleased();
      else if (heldInputs.size) {
        releaseLatch = true;
        releaseHint = releaseMessage;
        renderControls();
      }
      return;
    }
    if (!direction) return;
    event.preventDefault();
    if (!event.repeat) beginInput(token, direction, "keyboard", event.code);
  });
  window.addEventListener("keyup", (event) => {
    endInput(`key:${event.code}`);
  });
  window.addEventListener("blur", cancelAllInputs);
  document.addEventListener("visibilitychange", () => { if (document.hidden) cancelAllInputs(); });
  window.addEventListener("beforeunload", cancelAllInputs);
  window.addEventListener("pagehide", () => {
    leaving = true;
    clearTimeout(reconnect);
    cancelAllInputs();
    socket?.close();
  });
  // A frozen/stale status stream cannot keep browser commands alive.
  setInterval(() => {
    if (ready && performance.now() - lastStatusAt > 1000) {
      blockUntilReleased();
      ready = false;
      setConnection("Sin respuesta", "error");
      motionStatus.textContent = "Estado desactualizado · movimiento deshabilitado";
      renderControls();
    }
  }, 100);

  connect();
})();
