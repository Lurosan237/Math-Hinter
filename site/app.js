"use strict";

const NAMES = { llm_only: "Sans le cours", rag: "Avec le cours", agent: "Agent" };
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
        { left: "$", right: "$", display: false }],
      throwOnError: false,
    });
  }
  return node;
}

const lines = () => $("attempt").value.split("\n").map((l) => l.trimEnd()).filter((l) => l.trim());

/* The preview is the student's copy as it will be read: one numbered line per step. */
let flagged = null;
function preview() {
  $("preview-statement").textContent = $("statement").value.trim();
  const list = $("preview");
  list.replaceChildren(...lines().map((line, i) => {
    const li = el("li", { "data-n": i + 1, text: line });
    if (flagged && flagged.line === i) {
      li.classList.add("flagged");
      li.append(el("span", { class: "mark", "aria-label": "première ligne fausse", text: "✗" }));
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
  $("result").replaceChildren();
  $("status").textContent = "";
}

function passage(id, data) {
  return el("div", { class: "passage" },
    el("span", { class: "source", text: `${KINDS[data.kind] || ""} · ${data.label}` }), el("div", { text: data.text }));
}

function showResult(out, config) {
  const review = out.review;
  const box = $("result");
  const parts = [];
  if (review.failure) {
    parts.push(el("p", { class: "verdict", text: "Pas de réponse exploitable" }),
      el("p", { text: "Le modèle a répondu dans un format illisible. Relancez la relecture ; cela arrive à environ une "
        + "réponse sur vingt." }));
  } else if (review.verdict === "correct") {
    parts.push(el("p", { class: "verdict good", text: "Aucune erreur trouvée" }),
      el("p", { class: "aside", text: "Cela ne prouve pas que tout est juste : relisez aussi vous-même." }));
  } else {
    flagged = { line: review.first_wrong_line };
    parts.push(el("p", { class: "verdict bad", text: `Première erreur : ligne ${review.first_wrong_line + 1}` }));
    if (review.hint) parts.push(el("p", { class: "hint", text: review.hint }));
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
  box.replaceChildren(...parts);
  math(box);
  preview();
  if (window.matchMedia("(max-width: 860px)").matches) {
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("result").scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  }
}

async function submit(event) {
  event.preventDefault();
  clearResult();
  preview();
  const statement = $("statement").value.trim();
  const attempt = lines().join("\n");
  if (!statement) { $("status").textContent = "Écrivez d'abord l'énoncé."; $("statement").focus(); return; }
  if (!attempt) { $("status").textContent = "Écrivez votre rédaction, une étape par ligne."; $("attempt").focus(); return; }
  const config = document.querySelector("input[name=config]:checked").value;
  const key = $("key").value.trim();
  $("go").disabled = true;
  $("status").textContent = config === "agent" ? "L'agent relit et cherche dans le cours… (jusqu'à une minute)"
    : "Relecture en cours… (10 à 30 secondes)";
  try {
    const response = await fetch("/api/review", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ statement, attempt, config, key }),
    });
    const out = await response.json().catch(() => ({ error: `Le serveur a répondu ${response.status}.` }));
    if (!response.ok) {
      $("status").textContent = out.error || "La relecture a échoué.";
      if (["visitor", "site", "nokey"].includes(out.code)) $("own-key").open = true;
      return;
    }
    $("status").textContent = "";
    showResult(out, config);
  } catch {
    $("status").textContent = "Le serveur est injoignable. Vérifiez votre connexion et réessayez.";
  } finally {
    $("go").disabled = false;
  }
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
  const rows = ["llm_only", "rag", "agent"].map((key) => {
    const c = e.configs[key];
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
      + "verdict. Avec si peu d'exercices, les trois versions ne se distinguent pas. Cette évaluation a été faite sur "
      + "des manuels de Licence ; ce site cherche dans le cours Exo7, ce qui n'a pas été évalué." }),
    el("p", {}, el("a", { href: "https://github.com/Lurosan237/Math-Hinter/blob/main/reports/agent.md",
      text: "Lire le rapport complet" })));
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
  for (const id of ["statement", "attempt"]) $(id).addEventListener("input", () => { flagged = null; previewSoon(); });
  setUpExamples();
  setUpEvaluation();
  setUpChecker();
  const ready = setInterval(() => { if (window.renderMathInElement) { clearInterval(ready); preview(); } }, 100);
});
