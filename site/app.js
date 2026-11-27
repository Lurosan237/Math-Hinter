"use strict";

const NAMES = { pipeline: "Prudente", llm_only: "Directe", rag: "Avec le cours", agent: "Agent" };
const KINDS = { theorem: "Théorème", proposition: "Proposition", definition: "Définition", corollary: "Corollaire",
  lemma: "Lemme", example: "Exemple", proof: "Démonstration", heading: "Section" };
const $ = (id) => document.getElementById(id);
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else if (k === "text") node.textContent = v; else node.setAttribute(k, v);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
};

function math(node) {
  if (window.renderMathInElement) {
    renderMathInElement(node, {
      delimiters: [{ left: "\\[", right: "\\]", display: true }, { left: "$$", right: "$$", display: true },
        { left: "\\(", right: "\\)", display: false }, { left: "$", right: "$", display: false }],
      throwOnError: false,
    });
  }
  return node;
}

const lines = () => $("attempt").value.split("\n").map((l) => l.trimEnd()).filter((l) => l.trim());

/* The preview is the student's copy as it will be read: one numbered line per step. */
let flagged = null;
let unclear = new Set();
let marks = [];  // per line, from the computer: "verified", "refuted" or "unchecked"
function preview() {
  $("preview-statement").textContent = $("statement").value.trim();
  const list = $("preview");
  list.replaceChildren(...lines().map((line, i) => {
    const li = el("li", { "data-n": i + 1, text: line });
    if (unclear.has(i)) {
      li.classList.add("unclear");
      li.title = "Lecture incertaine : vérifiez cette ligne";
      if (!(flagged && flagged.line === i)) li.append(el("span", { class: "doubt", "aria-label": "lecture incertaine", text: "?" }));
    }
    if (marks[i] === "verified" && !(flagged && flagged.line === i)) {
      li.append(el("span", { class: "tick", title: "Calcul vérifié par l'ordinateur", "aria-label": "calcul vérifié",
        text: "✓" }));
    }
    if (flagged && flagged.line === i) {
      li.classList.add(flagged.doubt ? "doubtful" : "flagged");
      li.append(el("span", { class: flagged.doubt ? "doubt" : "mark",
        "aria-label": flagged.doubt ? "ligne à vérifier" : "première ligne fausse", text: flagged.doubt ? "?" : "✗" }));
    }
    return li;
  }));
  math($("preview-statement"));
  math(list);
}
let timer = null;
function previewSoon() { clearTimeout(timer); timer = setTimeout(preview, 250); }

function clearResult() {
  flagged = null;
  marks = [];
  $("result").replaceChildren();
  $("status").textContent = "";
}

function passage(id, data) {
  return el("div", { class: "passage" },
    el("span", { class: "source", text: `${KINDS[data.kind] || ""} · ${data.label}` }), el("div", { text: data.text }));
}

function showResult(out, config) {
  const review = out.review;
  if (out.split) {
    // The review numbered the steps it split; show the copy the same way so line numbers match.
    $("attempt").value = out.lines.join("\n");
    saveDraft();
  }
  const box = $("result");
  const parts = [];
  if (review.failure) {
    parts.push(el("p", { class: "verdict", text: "Pas de réponse exploitable" }),
      el("p", { text: "Le modèle a répondu dans un format illisible. Relancez la relecture ; cela arrive à environ une "
        + "réponse sur vingt." }));
  } else if (review.verdict === "correct") {
    parts.push(el("p", { class: "verdict good", text: "Aucune erreur trouvée" }),
      el("p", { class: "aside", text: "Cela ne prouve pas que tout est juste : relisez aussi vous-même." }));
    if (review.rejected) {
      // On the test set, most withdrawn flags were real errors: show the doubt plainly, as a doubt.
      flagged = { line: review.rejected.line, doubt: true };
      const doubt = el("div", { class: "doubt-box" },
        el("p", { class: "verdict doubt", text: `À vérifier : ligne ${review.rejected.line + 1}` }),
        el("blockquote", { class: "quoted", text: out.lines[review.rejected.line] || "" }),
        el("p", { class: "aside", text: "Une première lecture y voit une erreur que la seconde n'a pas confirmée. "
          + "C'est souvent une vraie erreur : relisez cette ligne." }));
      if (review.rejected.hint) doubt.append(el("p", { class: "hint", text: review.rejected.hint }));
      parts.push(doubt);
    }
  } else {
    flagged = { line: review.first_wrong_line };
    parts.push(el("p", { class: "verdict bad", text: `Première erreur : ligne ${review.first_wrong_line + 1}` }));
    const quoted = out.lines[review.first_wrong_line];
    if (quoted) parts.push(el("blockquote", { class: "quoted", text: quoted }));
    if (review.hint) {
      const ladder = el("div", { class: "hints" }, el("p", { class: "hint", text: review.hint }));
      parts.push(ladder);
      if (review.explanation) parts.push(moreHints(ladder, out, review));
    }
    if (review.explanation) parts.push(studyActions(out, review));
    remember(out, review);
  }
  if (review.explanation) {
    parts.push(el("details", {}, el("summary", { text: "Voir l'explication (elle peut donner la réponse)" }),
      el("p", { text: review.explanation })));
  }
  const cited = (review.citations || []).filter((id) => out.passages[id]);
  if (cited.length) {
    const d = el("details", { open: "" }, el("summary", { text: `Dans le cours (${cited.length})` }));
    cited.forEach((id) => d.append(passage(id, out.passages[id])));
    parts.push(d);
  }
  if (config === "agent" && review.tool_calls.length) {
    const steps = el("ol", { class: "trace" });
    for (const call of review.tool_calls) {
      if (call.tool === "search_course") steps.append(el("li", { text: `A cherché « ${call.query} » dans le cours` }));
      else if (call.tool === "check_equality") steps.append(el("li", { text: `A vérifié $${call.left} = ${call.right}$ : ${call.status}` }));
    }
    parts.push(el("details", {}, el("summary", { text: `Ce que l'agent a fait (${review.tool_calls.length})` }), steps));
  }
  const left = out.remaining == null ? "" : ` · ${out.remaining} relecture${out.remaining > 1 ? "s" : ""} restante${out.remaining > 1 ? "s" : ""} aujourd'hui`;
  parts.push(el("p", { class: "meta", text: `${NAMES[config]} · ${out.model} · ${out.seconds} s${left}` }));
  if (review.marks) {
    marks = review.marks;
    const checked = marks.filter((m) => m === "verified").length;
    if (checked) parts.push(el("p", { class: "aside", text: `✓ ${checked} ligne${checked > 1 ? "s" : ""} dont les calculs ont été refaits par l'ordinateur.` }));
  }
  box.replaceChildren(...parts);
  math(box);
  preview();
  if (window.matchMedia("(max-width: 860px)").matches) {
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("result").scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  }
}

/* Photos: resized in the browser so a phone picture fits the server's limit, then read by the vision model. */
const photos = [];
let photosRead = true;
const MAX_SIDE = 1600;

async function shrink(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = el("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

async function addPhotos(files) {
  for (const file of files) {
    if (photos.length >= 3) { $("status").textContent = "3 photos au plus."; break; }
    try { photos.push(await shrink(file)); } catch { $("status").textContent = "Cette image n'a pas pu être ouverte."; }
  }
  photosRead = false;
  showPhotos();
}

function showPhotos() {
  $("thumbs").replaceChildren(...photos.map((url, i) => {
    const remove = el("button", { type: "button", class: "remove", "aria-label": `Retirer la photo ${i + 1}`, text: "×" });
    remove.addEventListener("click", () => { photos.splice(i, 1); photosRead = false; showPhotos(); });
    const img = el("img", { src: url, alt: `Photo ${i + 1} de la copie` });
    img.addEventListener("click", () => window.open(url, "_blank"));
    return el("li", {}, img, remove);
  }));
  $("photo-tip").hidden = photos.length > 0;
  updateButton();
}

function updateButton() {
  const reading = photos.length && !photosRead;
  $("go").textContent = reading ? "Lire la photo et relire" : "Faire relire";
  $("reset").hidden = !(photos.length || $("statement").value || $("attempt").value);
}

/* A review streams its steps, one JSON per line, then {"status", "body"}. Older servers just send the body. */
async function postStreaming(path, payload, onStep) {
  const response = await fetch(path, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...payload, stream: true }),
  });
  if (!(response.headers.get("content-type") || "").includes("ndjson") || !response.body) {
    return finish(response, await response.json().catch(() => null));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", last = null;
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let cut;
    while ((cut = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 1);
      if (!line) continue;
      const data = JSON.parse(line);
      if (data.step) onStep(data.step); else last = data;
    }
    if (done) break;
  }
  if (!last) throw new Error("La relecture a été interrompue. Réessayez.");
  return finish({ ok: last.status === 200, status: last.status }, last.body);
}

function finish(response, out) {
  if (!out) out = { error: response.status === 504 ? "Le service a mis trop de temps à répondre. Réessayez dans une minute."
    : `Le serveur a répondu ${response.status}.` };
  if (!response.ok) {
    if (["visitor", "site", "nokey"].includes(out.code)) $("own-key").open = true;
    throw new Error(out.error || "La demande a échoué.");
  }
  return out;
}

/* Live steps, shown while the review runs. */
function stepList() {
  const list = el("ol", { class: "steps", "aria-live": "polite" });
  $("status").replaceChildren(list);
  return (step) => {
    let text = null;
    if (step.step === "reading") {
      if (list.lastChild && list.lastChild.dataset.kind === "reading") return;
      text = list.children.length ? "Relit la copie avec ce qu'il a trouvé…" : "Relit la copie…";
    } else if (step.step === "splitting") {
      text = "Découpe la rédaction en étapes, une par ligne…";
    } else if (step.step === "split") {
      text = `Rédaction découpée en ${step.steps} étapes`;
    } else if (step.step === "transcribing") {
      text = "Traduit chaque ligne en calculs vérifiables…";
    } else if (step.step === "checked") {
      const ok = step.checks.filter((c) => c.status === "vérifié").length;
      const bad = step.checks.filter((c) => c.status === "réfuté").length;
      text = step.checks.length ? `A refait ${step.checks.length} calcul${step.checks.length > 1 ? "s" : ""} : ${ok} juste${ok > 1 ? "s" : ""}`
        + (bad ? `, ${bad} faux` : "") : "Aucun calcul à refaire par l'ordinateur";
      marks = step.marks || [];
      preview();
    } else if (step.step === "confirming") {
      text = `Seconde lecture de la ligne ${step.line + 1} avant de la signaler…`;
    } else if (step.step === "passages") {
      text = `Énoncé du cours consulté : ${step.found.join(" ; ")}`;
    } else if (step.step === "tool" && step.tool === "search_course") {
      text = `A cherché « ${step.query} » dans le cours`
        + (step.found && step.found.length ? ` : ${step.found.join(" ; ")}` : " : rien trouvé");
    } else if (step.step === "tool" && step.tool === "check_equality") {
      text = `A vérifié $${step.left} = ${step.right}$ : ${step.status}`;
    }
    if (!text) return;
    [...list.children].forEach((li) => li.classList.add("done"));
    const li = el("li", { "data-kind": step.step, text });
    list.append(li);
    math(li);
  };
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload),
  });
  const out = await response.json().catch(() => ({
    error: response.status === 504 ? "Le service a mis trop de temps à répondre. Réessayez dans une minute."
      : `Le serveur a répondu ${response.status}.`,
  }));
  if (!response.ok) {
    if (["visitor", "site", "nokey"].includes(out.code)) $("own-key").open = true;
    throw new Error(out.error || "La demande a échoué.");
  }
  return out;
}

async function readPhotos(key) {
  $("status").textContent = "Lecture de la photo… (quelques secondes)";
  const out = await post("/api/transcribe", { images: photos, key });
  // The photo's statement replaces an empty one or an earlier reading, never one the student typed.
  if (out.statement && (!$("statement").value.trim() || $("statement").dataset.fromPhoto)) {
    $("statement").value = out.statement;
    $("statement").dataset.fromPhoto = "1";
  }
  $("attempt").value = out.lines.join("\n");
  unclear = new Set(out.unclear || []);
  photosRead = true;
  $("read-note").hidden = false;
  saveDraft();
  updateButton();
}

/* Up to two more hints, each more explicit, none giving the answer. */
function moreHints(ladder, out, review) {
  const given = [review.hint];
  const button = el("button", { type: "button", class: "more-hint", text: "Un autre indice" });
  const note = el("p", { class: "aside" });
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Un instant…";
    try {
      const reply = await post("/api/review?hint=1", {
        statement: $("statement").value.trim(), attempt: out.lines.join("\n"), key: $("key").value.trim(),
        line: review.first_wrong_line, hints: given, explanation: review.explanation, citations: review.citations,
      });
      given.push(reply.hint);
      const p = el("p", { class: "hint", text: reply.hint });
      ladder.append(el("span", { class: "hint-level", text: `Indice ${reply.level}` }), p);
      math(p);
      if (reply.last) {
        button.remove();
        note.textContent = "C'était le dernier indice. Si vous bloquez encore, l'explication ci-dessous donne la réponse.";
      }
    } catch (error) {
      note.textContent = error.message;
    } finally {
      button.disabled = false;
      if (button.isConnected) button.textContent = "Un autre indice";
    }
  });
  return el("div", { class: "hint-actions" }, button, note);
}

/* After an error: correct the line, talk it through, or practise the same skill. */
function studyActions(out, review) {
  const line = review.first_wrong_line;
  const area = el("div", { class: "study-area" });
  const fix = el("button", { type: "button", class: "study", text: `Corriger la ligne ${line + 1}` });
  const talk = el("button", { type: "button", class: "study", text: "Explique-moi" });
  const practise = el("button", { type: "button", class: "study", text: "Exercice du même type" });
  fix.addEventListener("click", () => area.replaceChildren(fixLine(out, line)));
  talk.addEventListener("click", () => area.replaceChildren(conversation(out, review)));
  practise.addEventListener("click", () => area.replaceChildren(similar($("statement").value.trim(),
    out.lines[line], review.explanation)));
  return el("div", { class: "study-block" }, el("div", { class: "study-buttons" }, fix, talk, practise), area);
}

function fixLine(out, line) {
  const input = el("textarea", { class: "fix-input", rows: "2", spellcheck: "false" });
  input.value = out.lines[line];
  const go = el("button", { type: "button", class: "go small", text: "Revérifier" });
  go.addEventListener("click", () => {
    const fixed = input.value.trim();
    if (!fixed) return;
    const all = lines();
    all[line] = fixed;
    $("attempt").value = all.join("\n");
    saveDraft();
    $("form").requestSubmit();
  });
  setTimeout(() => input.focus(), 0);
  return el("div", { class: "fix" }, el("label", { text: `Votre nouvelle ligne ${line + 1}` }), input, go);
}

function conversation(out, review) {
  const history = [];
  const list = el("div", { class: "chat", "aria-live": "polite" });
  const input = el("input", { type: "text", class: "chat-input", placeholder: "Votre question ou votre idée…" });
  const send = el("button", { type: "button", class: "go small", text: "Envoyer" });
  const say = async (text) => {
    if (text) {
      history.push({ role: "student", text });
      list.append(el("p", { class: "from-student", text }));
    }
    send.disabled = true;
    const waiting = el("p", { class: "from-tutor waiting", text: "…" });
    list.append(waiting);
    try {
      const reply = await post("/api/review?explain=1", {
        statement: $("statement").value.trim(), attempt: out.lines.join("\n"), line: review.first_wrong_line,
        explanation: review.explanation, history, key: $("key").value.trim(),
      });
      history.push({ role: "tutor", text: reply.reply });
      waiting.textContent = reply.reply;
      waiting.classList.remove("waiting");
      math(waiting);
    } catch (error) {
      waiting.textContent = error.message;
    } finally {
      send.disabled = false;
    }
  };
  const submitText = () => { const text = input.value.trim(); if (text) { input.value = ""; say(text); } };
  send.addEventListener("click", submitText);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); submitText(); } });
  say(`Je ne comprends pas pourquoi la ligne ${review.first_wrong_line + 1} est fausse.`);
  return el("div", { class: "explain" }, list, el("div", { class: "chat-row" }, input, send));
}

function similar(statement, line, explanation) {
  const box = el("div", { class: "practice" }, el("p", { class: "aside", text: "Préparation d'un exercice… (quelques secondes)" }));
  (async () => {
    try {
      const ex = await post("/api/review?similar=1", { statement, line, explanation, key: $("key").value.trim() });
      const answer = el("input", { type: "text", class: "chat-input", placeholder: "Votre réponse" });
      const check = el("button", { type: "button", class: "go small", text: "Vérifier ma réponse" });
      const verdict = el("p", { class: "aside", "aria-live": "polite" });
      const statementNode = el("p", { class: "practice-statement", text: ex.statement });
      check.addEventListener("click", async () => {
        if (!answer.value.trim()) return;
        check.disabled = true;
        try {
          const r = await post("/api/review?answer=1", { token: ex.token, answer: answer.value.trim() });
          verdict.className = r.status === "vérifié" ? "verdict good" : r.status === "réfuté" ? "verdict bad" : "aside";
          verdict.textContent = r.status === "vérifié" ? "Juste, vérifié par le calcul !"
            : r.status === "réfuté" ? "Pas encore : reprenez votre calcul." : "Je n'arrive pas à lire cette réponse : écrivez-la autrement.";
          if (r.status === "vérifié") practised(statement);
        } catch (error) {
          verdict.textContent = error.message;
        } finally {
          check.disabled = false;
        }
      });
      answer.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); check.click(); } });
      box.replaceChildren(el("p", { class: "practice-skill", text: `À travailler : ${ex.skill}` }), statementNode,
        el("label", { class: "aside", text: `Donnez ${ex.answer_label}, par exemple 2x+1 ou (e^2+1)/4 :` }),
        el("div", { class: "chat-row" }, answer, check), verdict);
      math(statementNode);
    } catch (error) {
      box.replaceChildren(el("p", { class: "aside", text: error.message }));
    }
  })();
  return box;
}

/* The mistake notebook, kept on this device only. */
const CATEGORIES = [
  ["Signes", /signe|moins|plus\b|négatif|positif/i], ["Exposants et puissances", /exposant|puissance|carré/i],
  ["Dérivées", /dériv/i], ["Intégrales et primitives", /intégr|primitive/i], ["Limites et développements", /limite|développement|équivalent/i],
  ["Sommes et suites", /somme|suite|série|géométrique|arithmétique/i], ["Hypothèses des théorèmes", /théorème|hypothèse|condition/i],
  ["Inégalités", /inégalit|majoration|minoration|≤|≥/i], ["Fractions", /fraction|dénominateur|numérateur|inverse/i],
];
const category = (text) => (CATEGORIES.find(([, pattern]) => pattern.test(text)) || ["Calculs"])[0];

function loadCarnet() { try { return JSON.parse(store.get("carnet") || "[]"); } catch { return []; } }

function remember(out, review) {
  const entries = loadCarnet();
  const statement = $("statement").value.trim();
  const line = out.lines[review.first_wrong_line] || "";
  if (entries.some((e) => e.statement === statement && e.line === line)) return;
  entries.unshift({ when: new Date().toISOString().slice(0, 10), statement, line, explanation: review.explanation,
    category: category(review.explanation), practised: false });
  store.set("carnet", JSON.stringify(entries.slice(0, 60)));
  showCarnet();
}

function practised(statement) {
  const entries = loadCarnet();
  entries.filter((e) => e.statement === statement).forEach((e) => { e.practised = true; });
  store.set("carnet", JSON.stringify(entries));
  showCarnet();
}

function showCarnet() {
  const entries = loadCarnet();
  const box = $("carnet");
  if (!entries.length) {
    box.replaceChildren(el("p", { class: "aside", text: "Rien pour l'instant : vos erreurs confirmées apparaîtront ici." }));
    return;
  }
  const counts = {};
  entries.forEach((e) => { counts[e.category] = (counts[e.category] || 0) + 1; });
  const summary = el("ul", { class: "carnet-summary" }, ...Object.entries(counts).sort((a, b) => b[1] - a[1])
    .map(([name, n]) => el("li", {}, el("b", { text: String(n) }), ` ${name}`)));
  const list = el("ol", { class: "carnet-list" }, ...entries.map((e) => {
    const area = el("div");
    const again = el("button", { type: "button", class: "study", text: e.practised ? "Encore un exercice" : "Exercice du même type" });
    again.addEventListener("click", () => area.replaceChildren(similar(e.statement, e.line, e.explanation)));
    const item = el("li", {}, el("span", { class: "carnet-meta", text: `${e.when} · ${e.category}${e.practised ? " · retravaillé ✓" : ""}` }),
      el("p", { class: "carnet-statement", text: e.statement.slice(0, 160) }), el("p", { class: "quoted", text: e.line }), again, area);
    math(item);
    return item;
  }));
  const clear = el("button", { type: "button", class: "reset", text: "Vider le carnet" });
  clear.addEventListener("click", () => { store.set("carnet", null); showCarnet(); });
  box.replaceChildren(summary, list, clear);
}

async function submit(event) {
  event.preventDefault();
  clearResult();
  const config = document.querySelector("input[name=config]:checked").value;
  const key = $("key").value.trim();
  $("go").disabled = true;
  try {
    if (photos.length && !photosRead) await readPhotos(key);
    preview();
    const statement = $("statement").value.trim();
    const attempt = lines().join("\n");
    if (!statement) { $("status").textContent = "Écrivez l'énoncé, ou photographiez-le avec la copie."; $("statement").focus(); return; }
    if (!attempt) { $("status").textContent = "Écrivez votre rédaction, ou photographiez-la."; $("attempt").focus(); return; }
    const out = await postStreaming("/api/review", { statement, attempt, config, key }, stepList());
    $("status").textContent = "";
    showResult(out, config);
  } catch (error) {
    $("status").textContent = error instanceof TypeError
      ? "Le serveur est injoignable. Vérifiez votre connexion et réessayez." : error.message;
  } finally {
    $("go").disabled = false;
  }
}

function saveDraft() {
  store.set("draft", JSON.stringify({ statement: $("statement").value, attempt: $("attempt").value }));
}

function resetAll() {
  photos.length = 0;
  photosRead = true;
  unclear = new Set();
  $("statement").value = "";
  $("attempt").value = "";
  delete $("statement").dataset.fromPhoto;
  $("read-note").hidden = true;
  store.set("draft", null);
  clearResult();
  showPhotos();
  preview();
  window.scrollTo({ top: 0 });
}

async function setUpExamples() {
  try {
    const data = await fetch("data/examples.json").then((r) => r.json());
    const box = $("examples");
    data.exercises.forEach((exercise) => {
      const button = el("button", { type: "button", text: exercise.title });
      button.addEventListener("click", () => {
        $("statement").value = exercise.statement;
        $("attempt").value = exercise.attempts.find((a) => a.kind === "wrong").text;
        photos.length = 0;
        photosRead = true;
        unclear = new Set();
        $("read-note").hidden = true;
        showPhotos();
        clearResult();
        preview();
        $("go").focus();
      });
      box.append(button);
    });
  } catch { /* examples are optional */ }
}

const pct = (x) => `${Math.round(x * 100)} %`;
async function setUpEvaluation() {
  let e;
  try { e = await fetch("data/agent.json").then((r) => r.json()); } catch { return; }
  let p = null;
  try { p = await fetch("data/pipeline.json").then((r) => r.json()); } catch { /* optional */ }
  const configs = { ...e.configs, ...(p ? { pipeline: p.configs.pipeline } : {}) };
  const rows = ["llm_only", "pipeline"].filter((key) => configs[key]).map((key) => {
    const c = configs[key];
    return el("tr", {}, el("th", { scope: "row", text: NAMES[key] }),
      el("td", { text: `${pct(c.both_right)}` }), el("td", { text: `${pct(c.both_right_ci95[0])} à ${pct(c.both_right_ci95[1])}` }),
      el("td", { text: pct(c.false_alarm) }));
  });
  $("evaluation").replaceChildren(
    el("p", { text: `Testé sur ${e.exercises} exercices de Licence mis de côté, chacun avec une copie contenant une `
      + "erreur connue et une copie juste. Une version réussit un exercice si elle trouve la ligne fausse exacte et ne "
      + "signale rien sur la copie juste." }),
    el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Version" }), el("th", { text: "Exercices réussis" }),
        el("th", { text: "Intervalle à 95 %" }), el("th", { text: "Fausses alertes" }))),
      el("tbody", {}, ...rows))),
    el("p", { text: "Autrement dit, il se trompe souvent : servez-vous de l'indice pour relire, pas comme d'un "
      + "verdict. La version prudente ne signale presque jamais à tort une copie juste, mais elle laisse passer bien "
      + "plus d'erreurs, qu'elle affiche alors comme des doutes à vérifier. Avec si peu d'exercices, ces chiffres "
      + "restent approximatifs. L'évaluation a été faite sur des manuels de Licence ; ce site cherche dans le cours "
      + "Exo7, ce qui n'a pas été évalué." }),
    el("p", {}, "Rapports complets : ",
      el("a", { href: "https://github.com/Lurosan237/Math-Hinter/blob/main/reports/agent.md", text: "version directe" }),
      ", ", el("a", { href: "https://github.com/Lurosan237/Math-Hinter/blob/main/reports/pipeline.md",
        text: "version prudente" }), "."));
  try {
    const t = (await fetch("data/transcription.json").then((r) => r.json())).summary;
    $("evaluation").append(el("p", { text: `Les photos : sur ${t.photos} copies d'exemple photographiées, `
      + `${t.lines_identical} lignes sur ${t.lines} ont été lues à l'identique et l'erreur de la copie n'a jamais été `
      + "corrigée en route. Ces pages étaient nettes et imprimées : une écriture réelle se lit moins bien, d'où "
      + "l'intérêt de vérifier la transcription avant de se fier à la relecture." }));
  } catch { /* the photo report is optional */ }
}

/* In-browser checker: the repository's own parser and checker, run by Pyodide. */
let python = null;
function startPython() {
  if (python) return python;
  python = (async () => {
    const script = el("script", { src: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js" });
    await new Promise((ok, fail) => { script.onload = ok; script.onerror = fail; document.head.append(script); });
    const py = await loadPyodide();
    await py.loadPackage("sympy");
    py.FS.mkdirTree("/home/pyodide/mathhinter/check");
    for (const name of ["__init__.py", "check/__init__.py", "check/parser.py", "check/equality.py"]) {
      py.FS.writeFile(`/home/pyodide/mathhinter/${name}`, await fetch(`py/mathhinter/${name}`).then((r) => r.text()));
    }
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')\nfrom mathhinter.check.equality import check_equality");
    return py;
  })();
  return python;
}
const REASONS = {
  identity: "les deux membres sont la même expression",
  "same number": "les deux membres valent le même nombre",
  "different numbers": "les deux membres sont deux nombres différents",
};
function setUpChecker() {
  const form = $("check-form"), out = $("check-result"), button = $("check-button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const left = $("left").value, right = $("right").value;
    button.disabled = true;
    out.textContent = python ? "Calcul…" : "Chargement de Python et SymPy…";
    try {
      const py = await startPython();
      py.globals.set("left", left);
      py.globals.set("right", right);
      const [status, reason] = py.runPython("v = check_equality(left, right); [v.status, v.reason]").toJs();
      const explained = REASONS[reason] || (reason.startsWith("unparseable") ? "expression illisible pour le vérificateur"
        : reason.startsWith("not an identity") ? "les membres diffèrent comme expressions : la ligne peut dépendre des précédentes"
          : reason);
      out.replaceChildren(el("span", { class: "status", text: status }), math(el("span", { text: `$${left} = ${right}$` })),
        el("br"), el("small", { text: explained }));
    } catch (error) {
      python = null;
      out.textContent = `Python n'a pas pu se charger (${error.message || error}).`;
    } finally {
      button.disabled = false;
    }
  });
}

window.addEventListener("DOMContentLoaded", () => {
  const saved = store.get("groq-key");
  if (saved) { $("key").value = saved; $("remember").checked = true; }
  $("remember").addEventListener("change", () => store.set("groq-key", $("remember").checked ? $("key").value.trim() : null));
  $("key").addEventListener("input", () => { if ($("remember").checked) store.set("groq-key", $("key").value.trim()); });
  $("form").addEventListener("submit", submit);
  for (const id of ["statement", "attempt"]) {
    $(id).addEventListener("input", () => {
      flagged = null;
      unclear = new Set();
      if (id === "statement") delete $("statement").dataset.fromPhoto;
      previewSoon();
      saveDraft();
      updateButton();
    });
  }
  for (const id of ["camera", "gallery"]) {
    $(id).addEventListener("change", (event) => { addPhotos([...event.target.files]); event.target.value = ""; });
  }
  $("reset").addEventListener("click", resetAll);
  try {
    const draft = JSON.parse(store.get("draft") || "null");
    if (draft) { $("statement").value = draft.statement || ""; $("attempt").value = draft.attempt || ""; }
  } catch { /* no draft */ }
  updateButton();
  setUpExamples();
  setUpEvaluation();
  showCarnet();
  setUpChecker();
  const ready = setInterval(() => { if (window.renderMathInElement) { clearInterval(ready); preview(); } }, 100);
});
