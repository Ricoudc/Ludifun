// Page /suivi : relit /suivi/donnees toutes les 3 secondes. Textes insérés avec textContent.
"use strict";

function duree(s) {
  if (s === null || s === undefined) return "en cours";
  if (s < 60) return s + " s";
  return Math.floor(s / 60) + " min " + String(s % 60).padStart(2, "0") + " s";
}

function quand(iso) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" });
}

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}

function ligne(cells) {
  const tr = document.createElement("tr");
  for (const cell of cells) tr.appendChild(cell instanceof Node ? wrap(cell) : el("td", cell));
  return tr;
}

function wrap(node) {
  const td = document.createElement("td");
  td.appendChild(node);
  return td;
}

function remplir(id, rows, vide, colonnes) {
  const body = document.getElementById(id);
  body.replaceChildren(...rows);
  if (!rows.length) {
    const td = el("td", vide, "muted");
    td.colSpan = colonnes;
    const tr = document.createElement("tr");
    tr.appendChild(td);
    body.appendChild(tr);
  }
}

function afficher(d) {
  document.getElementById("maj").textContent = quand(d.generated_at);
  document.getElementById("ia").textContent = d.server_ai;
  const familles = Object.entries(d.family_ai).map(([p, n]) => p + " (" + n + ")");
  document.getElementById("familles").textContent = familles.join(", ") || "aucune";

  const encours = document.getElementById("encours");
  encours.replaceChildren();
  for (const l of d.running) {
    const card = el("div", null, "card");
    card.appendChild(el("div", "Leçon " + l.lesson + " · " + l.status + " · " + l.source + ", " + l.pages +
      " page(s) · depuis " + duree(l.elapsed_s)));
    for (const c of l.calls) {
      card.appendChild(el("div", "⏳ " + c.stage + " avec " + c.model + " depuis " + duree(c.elapsed_s), "run"));
    }
    if (!l.calls.length) card.appendChild(el("div", "(entre deux appels à l'IA)", "muted"));
    encours.appendChild(card);
  }
  if (!d.running.length) encours.appendChild(el("p", "Aucune analyse en cours.", "muted"));

  remplir("lecons", d.recent.map((l) => {
    const etat = el("span", l.status + (l.failure ? " (" + l.failure + ")" : ""),
      l.state === "ready" ? "ok" : l.state === "failed" ? "bad" : "run");
    const etapes = el("div");
    for (const s of l.steps) {
      etapes.appendChild(el("div", s.stage + " : " + duree(s.seconds) + " · " + s.model + " · " + s.status,
        s.status === "ok" ? "" : "bad"));
      for (const note of s.notes || []) etapes.appendChild(el("div", "· " + note, "muted"));
    }
    return ligne([quand(l.created_at), l.lesson, etat, l.source + ", " + l.pages + " p.", duree(l.ai_s), etapes]);
  }), "Aucune leçon.", 6);

  remplir("stats", d.stats.map((s) =>
    ligne([s.model, s.stage, s.ok + " / " + s.calls, duree(s.median_s), duree(s.max_s)])), "Aucun appel.", 5);

  remplir("erreurs", d.errors.map((e) =>
    ligne([quand(e.at), e.lesson, e.stage, e.model, el("span", e.status, "bad"), e.message])), "Aucune erreur.", 6);
}

async function rafraichir() {
  try {
    const r = await fetch("/suivi/donnees", { cache: "no-store" });
    if (r.ok) afficher(await r.json());
    else document.getElementById("maj").textContent = "erreur " + r.status;
  } catch (e) {
    document.getElementById("maj").textContent = "serveur injoignable";
  }
}

rafraichir();
setInterval(rafraichir, 3000);
