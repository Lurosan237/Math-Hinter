"use strict";

const CONFIGS = [
  { key: "llm_only", name: "LLM seul", what: "Le modèle lit la copie, sans le cours." },
  { key: "rag", name: "LLM avec le cours", what: "On lui joint cinq passages du cours trouvés par recherche." },
  { key: "agent", name: "Agent", what: "Il cherche lui-même dans le cours et peut vérifier une égalité." },
];
const state = { exercise: 0, attempt: "wrong" };
let data = null;

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
      delimiters: [{ left: "\\[", right: "\\]", display: true }, { left: "$", right: "$", display: false }],
      throwOnError: false,
    });
  }
  return node;
}

async function load() {
  const get = (name) => fetch(`data/${name}`).then((r) => { if (!r.ok) throw new Error(name); return r.json(); });
  const [exercises, runs, corpus, evaluation] = await Promise.all(
    ["exercises.json", "runs.json", "corpus.json", "agent.json"].map(get));
  const units = new Map(corpus.units.map((u) => [u.id, u]));
  data = { exercises: exercises.exercises, runs, units, evaluation };
}

function judge(attempt, review) {
  if (review.failure) return { good: false, text: "réponse invalide" };
  if (attempt.kind === "control") {
    return review.verdict === "correct" ? { good: true, text: "juste, rien à signaler" }
      : { good: false, text: "fausse alerte" };
  }
  if (review.verdict !== "wrong") return { good: false, text: "erreur manquée" };
  return review.first_wrong_line === attempt.wrong_line
    ? { good: true, text: `ligne ${review.first_wrong_line}, bien vu` }
    : { good: false, text: `ligne ${review.first_wrong_line} au lieu de ${attempt.wrong_line}` };
}

function passage(id) {
  const unit = data.units.get(id);
  if (!unit) return el("p", { class: "passage", text: `${id} (passage introuvable)` });
  return el("div", { class: "passage" }, el("span", { class: "source", text: unit.label || id }),
    el("div", { text: unit.text.slice(0, 900) }));
}

function reviewCard(exercise, attempt, config) {
  const review = data.runs.reviews.find((r) => r.exercise === exercise.id && r.attempt === attempt.kind
    && r.config === config.key);
  const card = el("section", { class: "review" });
  const head = el("header", {}, el("h4", { text: config.name }));
  card.append(head, el("p", { class: "what", text: config.what }));
  if (!review) {
    card.append(el("p", { text: "Pas encore enregistrée." }));
    return card;
  }
  const verdict = judge(attempt, review);
  head.append(el("span", { class: `verdict ${verdict.good ? "good" : "bad"}`, text: verdict.text }));
  if (review.verdict === "wrong" && review.hint) card.append(el("p", { class: "hint", text: review.hint }));
  if (review.explanation) {
    card.append(el("details", {}, el("summary", { text: "Explication" }), el("p", { text: review.explanation })));
  }
  if (config.key === "agent" && review.tool_calls.length) {
    const steps = el("ol", { class: "trace" });
    for (const call of review.tool_calls) {
      if (call.tool === "search_course") steps.append(el("li", { text: `Recherche dans le cours : « ${call.query} »` }));
      else if (call.tool === "check_equality") {
        steps.append(el("li", { text: `Vérifie $${call.left} = ${call.right}$ : ${call.status}` }));
      } else steps.append(el("li", { text: call.tool }));
    }
    card.append(el("details", {}, el("summary", { text: `Étapes (${review.tool_calls.length})` }), steps));
  }
  const cited = (review.citations || []).filter((id) => data.units.has(id));
  if (cited.length) {
    const box = el("details", {}, el("summary", { text: `Cours cité (${cited.length})` }));
    cited.forEach((id) => box.append(passage(id)));
    card.append(box);
  }
  return card;
}

function render() {
  const exercise = data.exercises[state.exercise];
  const attempt = exercise.attempts.find((a) => a.kind === state.attempt);
  document.querySelectorAll("#exercises button").forEach((b, i) => b.setAttribute("aria-current", i === state.exercise));
  document.querySelectorAll(".copy-switch button").forEach((b) =>
    b.setAttribute("aria-checked", b.dataset.attempt === state.attempt));

  const sheet = document.getElementById("sheet");
  const lines = el("ol", { class: "attempt", start: "0" });
  attempt.text.split("\n").forEach((line, i) => lines.append(el("li", { "data-n": i, text: line })));
  const planted = attempt.kind === "wrong"
    ? el("details", { class: "planted" }, el("summary", { text: "Voir l'erreur placée dans la copie" }),
      el("p", { text: `Ligne ${attempt.wrong_line}. ${attempt.note}` }))
    : el("p", { class: "planted", text: "Cette copie ne contient pas d'erreur : une bonne relecture ne signale rien." });
  sheet.replaceChildren(el("h3", { text: exercise.title }), el("p", { class: "statement", text: exercise.statement }),
    lines, planted);
  planted.addEventListener?.("toggle", () => {
    const li = lines.children[attempt.wrong_line];
    if (!li) return;
    li.classList.toggle("flagged", planted.open);
    if (planted.open) li.append(el("span", { class: "mark", text: "✗" }));
    else li.querySelector(".mark")?.remove();
  });

  const reviews = document.getElementById("reviews");
  reviews.replaceChildren(...CONFIGS.map((c) => reviewCard(exercise, attempt, c)));
  math(sheet);
  math(reviews);
}

function setUp() {
  const nav = document.getElementById("exercises");
  data.exercises.forEach((exercise, i) => {
    const button = el("button", { type: "button", text: exercise.title });
    button.addEventListener("click", () => { state.exercise = i; render(); });
    nav.append(button);
  });
  document.querySelectorAll(".copy-switch button").forEach((b) => b.addEventListener("click", () => {
    state.attempt = b.dataset.attempt; render();
  }));
  const reviews = data.runs.reviews;
  const right = reviews.filter((r) => {
    const exercise = data.exercises.find((e) => e.id === r.exercise);
    return judge(exercise.attempts.find((a) => a.kind === r.attempt), r).good;
  }).length;
  document.getElementById("recorded").textContent = `Réponses enregistrées une fois avec le modèle ${data.runs.model} `
    + `(via Groq, température 0), sans appel en direct depuis cette page. Sur ces ${data.exercises.length} exercices `
    + `écrits pour la démonstration, ${right} réponses sur ${reviews.length} sont justes : c'est trop peu pour `
    + "comparer les versions. Les chiffres de l'évaluation sont plus bas.";
  renderEvaluation();
  render();
}

const pct = (x) => `${Math.round(x * 100)} %`;

function renderEvaluation() {
  const e = data.evaluation;
  const names = { llm_only: "LLM seul", rag: "LLM avec le cours", agent: "Agent" };
  const rows = Object.entries(names).map(([key, name]) => {
    const c = e.configs[key];
    return el("tr", {}, el("th", { scope: "row", text: name }),
      el("td", { text: `${pct(c.both_right)} (${pct(c.both_right_ci95[0])} à ${pct(c.both_right_ci95[1])})` }),
      el("td", { text: pct(c.exact_line) }), el("td", { text: pct(c.false_alarm) }),
      el("td", { text: String(c.tokens_per_review) }));
  });
  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "Version" }), el("th", { text: "Les deux copies bien jugées (IC 95 %)" }),
      el("th", { text: "Bonne ligne" }), el("th", { text: "Fausse alerte" }), el("th", { text: "Jetons par copie" }))),
    el("tbody", {}, ...rows));
  const d = e.agent_minus_llm_only;
  document.getElementById("evaluation").replaceChildren(
    el("p", { class: "finding", text: `Sur ${e.exercises} exercices tenus à l'écart, le cours et l'agent ne font pas mieux `
      + "que le modèle seul." }),
    el("p", { text: "Chaque exercice a une copie avec une erreur connue et une copie juste. Une version réussit un "
      + "exercice si elle trouve la ligne fausse exacte et laisse la copie juste tranquille. Les exercices viennent "
      + "des manuels de Licence, pas de cette page." }),
    el("div", { class: "table-wrap" }, table),
    el("p", { text: `Écart agent moins LLM seul : ${Math.round(d.difference * 100)} points (IC 95 % de `
      + `${Math.round(d.ci95[0] * 100)} à ${Math.round(d.ci95[1] * 100)}). Choisir une ligne au hasard donnerait la `
      + `bonne ${pct(e.chance_exact_line)} du temps. L'agent a cherché ${e.agent_usage.searches} fois dans le cours `
      + `et n'a jamais utilisé le vérificateur ; toutes ses ${e.agent_usage.citations} citations renvoient à des `
      + "passages qu'il avait vraiment lus." }),
    el("p", {}, "Détails, limites et vérifications à la main : ",
      el("a", { href: "https://github.com/Lurosan237/Math-Hinter/blob/main/reports/agent.md", text: "le rapport" }), "."));
}

/* In-browser checker: the repository's own parser and checker, run by Pyodide. */
let python = null;
async function startPython() {
  if (python) return python;
  python = (async () => {
    const script = el("script", { src: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js" });
    await new Promise((ok, fail) => { script.onload = ok; script.onerror = fail; document.head.append(script); });
    const py = await loadPyodide();
    await py.loadPackage("sympy");
    py.FS.mkdirTree("/home/pyodide/mathhinter/check");
    for (const name of ["__init__.py", "check/__init__.py", "check/parser.py", "check/equality.py"]) {
      const text = await fetch(`py/mathhinter/${name}`).then((r) => r.text());
      py.FS.writeFile(`/home/pyodide/mathhinter/${name}`, text);
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
  const form = document.getElementById("check-form");
  const out = document.getElementById("check-result");
  const button = document.getElementById("check-button");
  document.querySelectorAll(".examples button").forEach((b) => b.addEventListener("click", () => {
    document.getElementById("left").value = b.dataset.l;
    document.getElementById("right").value = b.dataset.r;
    form.requestSubmit();
  }));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const left = document.getElementById("left").value, right = document.getElementById("right").value;
    button.disabled = true;
    out.textContent = python ? "Calcul…" : "Chargement de Python et SymPy…";
    try {
      const py = await startPython();
      py.globals.set("left", left);
      py.globals.set("right", right);
      const [status, reason] = py.runPython("v = check_equality(left, right); [v.status, v.reason]").toJs();
      const explained = REASONS[reason] || (reason.startsWith("unparseable") ? `lecture impossible (${reason.slice(13)})`
        : reason.startsWith("not an identity") ? "les deux membres diffèrent comme expressions : la ligne peut dépendre des précédentes"
          : reason);
      out.replaceChildren(el("span", { class: `status ${status === "vérifié" ? "good" : ""}`, text: status }),
        math(el("span", { text: `$${left} = ${right}$` })), el("br"), el("small", { text: explained }));
    } catch (error) {
      python = null;
      out.textContent = `Python n'a pas pu se charger (${error.message || error}). Vérifiez la connexion et réessayez.`;
    } finally {
      button.disabled = false;
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  setUpChecker();
  try {
    await load();
    setUp();
  } catch (error) {
    document.getElementById("sheet").textContent = `Les données de la démonstration n'ont pas pu se charger (${error.message}).`;
  }
});
