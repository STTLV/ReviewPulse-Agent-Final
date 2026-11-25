"use strict";

// Cliente SSE sin bibliotecas externas. El código de acceso permanece solo
// en el formulario y se envía en X-Codigo-Acceso, nunca en la URL ni en almacenamiento persistente.
const ui = {
  form: document.getElementById("chat-form"),
  code: document.getElementById("codigo"),
  input: document.getElementById("mensaje"),
  send: document.getElementById("enviar"),
  cancel: document.getElementById("cancelar"),
  messages: document.getElementById("chat-messages"),
  trace: document.getElementById("trace-list"),
  traceState: document.getElementById("trace-state"),
  stepCount: document.getElementById("step-count"),
  liveDot: document.getElementById("live-dot"),
  status: document.getElementById("status-text"),
  statusDot: document.getElementById("status-dot"),
  feedback: document.getElementById("form-feedback"),
  clearTrace: document.getElementById("clear-trace"),
};
let inFlight = false;
let abortController = null;
let steps = 0;

function setActivity(active) {
  inFlight = active;
  ui.send.disabled = active;
  ui.input.disabled = active;
  ui.code.disabled = active;
  ui.cancel.hidden = !active;
  document.querySelectorAll("[data-prompt]").forEach((button) => { button.disabled = active; });
  ui.liveDot.classList.toggle("active", active);
  ui.traceState.textContent = active ? "En vivo" : "En espera";
}

// Formato limitado y seguro para respuestas: negrita y codigo en linea.
// Se crean nodos DOM con textContent, nunca se interpreta HTML del modelo.
function setAssistantText(target, content) {
  const parts = String(content).split(/(\*\*[^*\r\n]+\*\*|`[^`\r\n]+`)/g);
  const fragment = document.createDocumentFragment();
  for (const part of parts) {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const strong = document.createElement("strong");
      strong.textContent = part.slice(2, -2);
      fragment.appendChild(strong);
    } else if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      const code = document.createElement("code");
      code.textContent = part.slice(1, -1);
      fragment.appendChild(code);
    } else if (part) {
      fragment.appendChild(document.createTextNode(part));
    }
  }
  target.replaceChildren(fragment);
}

function addMessage(who, content) {
  const row = document.createElement("div");
  row.className = `message ${who}`;
  if (who === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "R";
    row.appendChild(avatar);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const author = document.createElement("p");
  author.className = "message-author";
  author.textContent = who === "assistant" ? "ReviewPulse" : "Tú";
  const text = document.createElement("div");
  text.className = "message-text";
  text.textContent = content; // Nunca interpretar el texto del agente como HTML.
  body.append(author, text);
  row.appendChild(body);
  ui.messages.appendChild(row);
  ui.messages.scrollTop = ui.messages.scrollHeight;
  return { body, text };
}

function addNotice(messageBody, aviso) {
  if (!aviso) return;
  const notice = document.createElement("div");
  notice.className = "demo-notice";
  notice.textContent = aviso;
  messageBody.insertBefore(notice, messageBody.querySelector(".message-text"));
}

function clearTrace() {
  ui.trace.replaceChildren();
  const empty = document.createElement("li");
  empty.className = "empty-trace";
  empty.id = "trace-empty";
  const symbol = document.createElement("div");
  symbol.className = "empty-icon";
  symbol.textContent = "◎";
  symbol.setAttribute("aria-hidden", "true");
  const title = document.createElement("strong");
  title.textContent = "Aún no hay eventos";
  const description = document.createElement("span");
  description.textContent = "Aquí aparecen los pasos cuando la pregunta coincide con una grabación.";
  empty.append(symbol, title, description);
  ui.trace.appendChild(empty);
  steps = 0;
  ui.stepCount.textContent = "0 eventos";
}

function addTrace(eventData, isError = false) {
  const empty = document.getElementById("trace-empty");
  if (empty) empty.remove();
  steps += 1;
  const item = document.createElement("li");
  item.className = `trace-event${isError ? " error" : ""}`;
  const number = document.createElement("span");
  number.className = "event-number";
  number.textContent = `PASO ${String(steps).padStart(2, "0")}`;
  const title = document.createElement("h3");
  const fase = typeof eventData.fase === "string" ? eventData.fase : "SISTEMA";
  const evento = typeof eventData.evento === "string" ? eventData.evento : "evento";
  title.textContent = `${fase} · ${evento.replaceAll("_", " ")}`;
  const detail = document.createElement("p");
  if (evento === "reproduccion_demo") {
    detail.textContent = eventData.aviso_demo || "Se reproduce una conversación grabada.";
  } else if (evento === "herramienta") {
    detail.textContent = `Herramienta: ${eventData.herramienta || "sin nombre"}`;
  } else if (evento === "tarea_recibida") {
    detail.textContent = "Pregunta recibida para su análisis.";
  } else if (evento === "respuesta_llm") {
    detail.textContent = "El modelo devolvió un paso de trabajo.";
  } else if (evento === "respuesta_final") {
    detail.textContent = "Respuesta final generada.";
  } else {
    detail.textContent = "Evento registrado por la API.";
  }
  const more = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Ver datos del evento";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(eventData, null, 2);
  more.append(summary, pre);
  item.append(number, title, detail, more);
  ui.trace.appendChild(item);
  ui.stepCount.textContent = `${steps} ${steps === 1 ? "evento" : "eventos"}`;
  ui.trace.scrollTop = ui.trace.scrollHeight;
}

function consumeBlock(block, onEvent) {
  let eventName = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;
  let data;
  try { data = JSON.parse(dataLines.join("\n")); }
  catch { throw new Error("La API devolvió un evento SSE inválido."); }
  onEvent(eventName, data);
}

async function readSSE(response, onEvent, signal) {
  if (!response.body) throw new Error("El navegador no admite la respuesta en vivo.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n?/g, "\n");
      if (buffer.length > 2_000_000) throw new Error("La respuesta es demasiado extensa.");
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        consumeBlock(block, onEvent);
      }
      if (signal.aborted) break;
    }
    buffer += decoder.decode();
    if (buffer.trim() && !signal.aborted) consumeBlock(buffer, onEvent);
  } finally {
    if (signal.aborted) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function sendChat(event) {
  event.preventDefault();
  if (inFlight) return;
  const message = ui.input.value.trim();
  const code = ui.code.value;
  if (!message || !code.trim()) {
    ui.feedback.textContent = "Escribe una pregunta e introduce el código de acceso.";
    return;
  }
  ui.feedback.textContent = "";
  clearTrace();
  addMessage("user", message);
  const assistant = addMessage("assistant", "Analizando la consulta…");
  ui.input.value = "";
  const controller = new AbortController();
  abortController = controller;
  setActivity(true);
  let finished = false;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Codigo-Acceso": code },
      body: JSON.stringify({ mensaje: message }),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("Código de acceso incorrecto.");
      if (response.status === 429) throw new Error("El agente está ocupado. Inténtalo nuevamente.");
      throw new Error(`No se pudo iniciar el chat (HTTP ${response.status}).`);
    }
    await readSSE(response, (name, data) => {
      if (name === "paso") {
        addTrace(data.traza || data);
      } else if (name === "final") {
        if (data.modo_demo && data.coincidencia_demo === false) {
          // Sin coincidencia, mostrar un único aviso; nunca una respuesta
          // o traza perteneciente a una pregunta diferente.
          setAssistantText(assistant.text, data.aviso_demo || data.texto ||
            "Modo demostración: no hay una conversación grabada para esta consulta.");
        } else {
          setAssistantText(assistant.text, data.texto || "La respuesta llegó vacía.");
          if (data.modo_demo) {
            addNotice(assistant.body,
              data.aviso_demo || "Modo demostración: conversación grabada.");
          }
        }
        finished = true;
      } else if (name === "error") {
        addTrace({ fase: "SISTEMA", evento: "error", ...data }, true);
        assistant.text.textContent = data.mensaje || "Ocurrió un error durante el análisis.";
        finished = true;
      }
      ui.messages.scrollTop = ui.messages.scrollHeight;
    }, controller.signal);
    if (!finished && !controller.signal.aborted) {
      assistant.text.textContent = "La transmisión terminó sin una respuesta final. Puedes volver a intentarlo.";
    }
  } catch (error) {
    assistant.text.textContent = controller.signal.aborted
      ? "Solicitud cancelada."
      : (error instanceof Error ? error.message : "No fue posible contactar la API.");
  } finally {
    if (abortController === controller) abortController = null;
    setActivity(false);
    ui.messages.scrollTop = ui.messages.scrollHeight;
    ui.input.focus();
  }
}

ui.form.addEventListener("submit", sendChat);
ui.cancel.addEventListener("click", () => { if (abortController) abortController.abort(); });
ui.clearTrace.addEventListener("click", () => { if (!inFlight) clearTrace(); });
ui.input.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    if (ui.form.requestSubmit) ui.form.requestSubmit();
  }
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => { ui.input.value = button.dataset.prompt || ""; ui.input.focus(); });
});

(async function healthCheck() {
  try {
    const response = await fetch("/api/salud", { cache: "no-store" });
    if (!response.ok) throw new Error("API no disponible");
    ui.statusDot.classList.add("good");
    ui.status.textContent = "API disponible";
  } catch {
    ui.statusDot.classList.add("bad");
    ui.status.textContent = "No se pudo conectar con la API";
  }
})();
