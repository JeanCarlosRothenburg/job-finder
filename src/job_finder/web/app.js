"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MODELO = { remoto: "Remoto", hibrido: "Híbrido", presencial: "Presencial" };
const SENIOR = { junior: "Júnior", pleno: "Pleno", senior: "Sênior", estagio: "Estágio", especialista: "Especialista" };
let pilha = [];
let historico = []; // ids recusados/confirmados para desfazer
let corte = 8;

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { headers: { "Content-Type": "application/json" }, ...opcoes,
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  const tipo = r.headers.get("content-type") || "";
  return tipo.includes("json") ? r.json() : r.text();
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 2600);
}

function data(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function metaVaga(v) {
  const local = [v.cidade, v.uf].filter(Boolean).join("/");
  const itens = [
    MODELO[v.modelo] || "Modelo não informado",
    local,
    SENIOR[v.senioridade],
    v.contrato ? v.contrato.toUpperCase() : "",
    v.salario,
    v.fonte,
    v.publicada_em ? "Publicada " + new Date(v.publicada_em).toLocaleDateString("pt-BR") : "",
  ].filter(Boolean).map((t) => `<span>${esc(t)}</span>`);
  for (const a of v.analise?.avisos || []) itens.push(`<span class="alerta">${esc(a)}</span>`);
  if (v.revisada_claude) itens.push(`<span>Revisada pelo Claude</span>`);
  return `<div class="meta">${itens.join("")}</div>`;
}

function grupos(a) {
  if (!a) return "";
  const g = (cls, titulo, lista) => lista?.length ? `<div class="grupo ${cls}"><h4>${titulo}</h4><ul>${lista.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  return g("prof", "Atende com experiência", a.atende_profissional) + g("conh", "Só conhecimento", a.atende_conhecimento) + g("falta", "Falta", a.nao_atende);
}

// ---------------------------------------------------------------- Pilha
function renderPilha() {
  const el = $("#pilha");
  el.innerHTML = "";
  $("#c-pilha").textContent = pilha.length || "";
  if (!pilha.length) {
    el.innerHTML = `<div class="vazio">Nenhuma vaga compatível agora.<br>A busca roda sozinha a cada poucas horas.</div>`;
    return;
  }
  pilha.slice(0, 2).reverse().forEach((v, i, arr) => {
    const c = document.createElement("article");
    c.className = "cartao" + (i < arr.length - 1 ? " atras" : "");
    c.dataset.id = v.id;
    c.innerHTML = `
      <div class="carimbo sim">CONFIRMAR</div><div class="carimbo nao">RECUSAR</div>
      <div class="topo"><div><h3>${esc(v.titulo)}</h3><div class="empresa">${esc(v.empresa || "Empresa não informada")}</div></div>
      <div class="nota ${v.nota < corte ? "media" : ""}">${v.nota ?? "–"}</div></div>
      ${metaVaga(v)}
      ${v.observacao_claude ? `<p><b>Claude:</b> ${esc(v.observacao_claude)}</p>` : ""}
      ${grupos(v.analise)}
      <p><button class="link" data-desc="${v.id}">Ver descrição completa</button> · <a href="${esc(v.url)}" target="_blank" rel="noopener">Abrir vaga</a></p>`;
    el.appendChild(c);
    if (i === arr.length - 1) ativarArraste(c);
  });
}

function ativarArraste(c) {
  let x0 = null, dx = 0;
  c.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button, a")) return;
    x0 = e.clientX; dx = 0; c.setPointerCapture(e.pointerId); c.classList.add("arrastando");
  });
  c.addEventListener("pointermove", (e) => {
    if (x0 === null) return;
    dx = e.clientX - x0;
    c.style.transform = `translateX(${dx}px) rotate(${dx / 20}deg)`;
    $(".carimbo.sim", c).style.opacity = Math.max(0, Math.min(1, dx / 120));
    $(".carimbo.nao", c).style.opacity = Math.max(0, Math.min(1, -dx / 120));
  });
  const fim = () => {
    if (x0 === null) return;
    x0 = null; c.classList.remove("arrastando");
    if (dx > 120) decidir("confirmar");
    else if (dx < -120) decidir("recusar");
    else { c.style.transform = ""; c.querySelectorAll(".carimbo").forEach((k) => (k.style.opacity = 0)); }
  };
  c.addEventListener("pointerup", fim);
  c.addEventListener("pointercancel", fim);
}

async function decidir(decisao) {
  const v = pilha[0];
  if (!v) return;
  const c = $(`.cartao[data-id="${v.id}"]`);
  if (c) {
    c.style.transform = `translateX(${decisao === "confirmar" ? 700 : -700}px) rotate(${decisao === "confirmar" ? 25 : -25}deg)`;
    c.style.opacity = 0;
  }
  try {
    await api(`/api/vagas/${v.id}/decisao`, { method: "POST", body: { decisao } });
    historico.push(v);
    pilha.shift();
    setTimeout(renderPilha, 220);
    toast(decisao === "confirmar" ? "Confirmada: veja a aba Candidatar" : "Recusada");
    atualizarContadores();
  } catch (e) { toast(e.message); renderPilha(); }
}

async function desfazer() {
  const v = historico.pop();
  if (!v) return toast("Nada para desfazer");
  try {
    await api(`/api/vagas/${v.id}/desfazer`, { method: "POST" });
    pilha.unshift(v); renderPilha(); atualizarContadores();
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- Candidatar
function blocoTexto(rotulo, campo, valor, linhas = 5) {
  return `<div class="bloco-texto"><label>${rotulo}</label><textarea data-campo="${campo}" rows="${linhas}">${esc(valor)}</textarea>
    <button class="sec" data-copiar="${campo}">Copiar</button></div>`;
}

async function renderCandidatar() {
  const vagas = await api("/api/vagas?status=em_candidatura");
  $("#c-candidatar").textContent = vagas.length || "";
  const el = $("#lista-candidatar");
  if (!vagas.length) { el.innerHTML = `<p class="dica">Nenhuma vaga confirmada aguardando envio.</p>`; return; }
  el.innerHTML = vagas.map((v) => {
    const c = v.candidatura || {};
    const sem = !(c.texto_formal || c.mensagem_recrutador);
    return `<div class="item" data-id="${v.id}">
      <div class="cab"><div><b>${esc(v.titulo)}</b> · ${esc(v.empresa)}<br><small>${esc(MODELO[v.modelo] || "")} ${esc(v.cidade)} · nota ${v.nota}</small></div>
      <small>${sem ? "Aguardando textos do Claude" : "Textos prontos"}</small></div>
      ${blocoTexto("Texto da Gupy: versão formal", "texto_formal", c.texto_formal)}
      ${blocoTexto("Texto da Gupy: versão leve", "texto_leve", c.texto_leve)}
      <div class="bloco-texto"><label>3 skills da Gupy (separadas por vírgula)</label><input data-campo="skills_gupy" value="${esc((c.skills_gupy || []).join(", "))}"></div>
      ${blocoTexto(`Mensagem ao recrutador${v.recrutador_nome ? " (" + esc(v.recrutador_nome) + ")" : ""}`, "mensagem_recrutador", c.mensagem_recrutador, 3)}
      ${c.texto_preferencial ? blocoTexto("Por que a vaga é preferencial (LinkedIn)", "texto_preferencial", c.texto_preferencial, 3) : ""}
      <div class="botoes">
        <a href="${esc(v.url)}" target="_blank" rel="noopener"><button>Abrir vaga</button></a>
        ${v.recrutador_url ? `<a href="${esc(v.recrutador_url)}" target="_blank" rel="noopener"><button class="sec">Abrir recrutador</button></a>` : ""}
        <button class="sec" data-acao="claude">Copiar para o Claude</button>
        <button class="sec" data-acao="salvar">Salvar edições</button>
        <button data-acao="enviada">Marcar como enviada</button>
        <button class="sec" data-acao="voltar">Voltar para a pilha</button>
      </div></div>`;
  }).join("");
}

function camposDe(item) {
  const d = {};
  item.querySelectorAll("[data-campo]").forEach((i) => {
    d[i.dataset.campo] = i.dataset.campo === "skills_gupy" ? i.value.split(",").map((s) => s.trim()).filter(Boolean) : i.value;
  });
  return d;
}

$("#lista-candidatar").addEventListener("click", async (e) => {
  const item = e.target.closest(".item");
  if (!item) return;
  const id = item.dataset.id;
  const cop = e.target.dataset.copiar;
  if (cop) {
    await navigator.clipboard.writeText($(`[data-campo="${cop}"]`, item).value);
    return toast("Copiado");
  }
  const acao = e.target.dataset.acao;
  try {
    if (acao === "claude") {
      await navigator.clipboard.writeText(await api(`/api/vagas/${id}/para-claude`));
      toast("Vaga copiada; cole numa conversa com o Claude");
    } else if (acao === "salvar") {
      await api(`/api/vagas/${id}/candidatura`, { method: "PATCH", body: camposDe(item) });
      toast("Salvo");
    } else if (acao === "enviada") {
      await api(`/api/vagas/${id}/candidatura`, { method: "PATCH", body: camposDe(item) });
      await api(`/api/vagas/${id}/enviada`, { method: "POST", body: {} });
      toast("Candidatura registrada"); renderCandidatar(); atualizarContadores();
    } else if (acao === "voltar") {
      await api(`/api/vagas/${id}/desfazer`, { method: "POST" });
      toast("Voltou para a pilha"); renderCandidatar(); carregarPilha();
    }
  } catch (err) { toast(err.message); }
});

// ---------------------------------------------------------------- Realizadas
let realizadas = [];
async function renderRealizadas() {
  realizadas = await api("/api/vagas?status=candidatada");
  $("#c-realizadas").textContent = realizadas.length || "";
  desenharRealizadas();
}
function desenharRealizadas() {
  const f = $("#filtro-realizadas").value.toLowerCase();
  $("#tabela-realizadas tbody").innerHTML = realizadas
    .filter((v) => !f || (v.titulo + " " + v.empresa).toLowerCase().includes(f))
    .map((v) => `<tr data-id="${v.id}"><td>${esc(data(v.candidatura?.enviada_em))}</td><td>${esc(v.titulo)}</td><td>${esc(v.empresa)}</td>
      <td>${v.nota ?? ""}</td><td>${esc(v.candidatura?.canal)}</td>
      <td><input data-obs value="${esc(v.candidatura?.observacoes)}" placeholder="ex.: recrutador respondeu"></td>
      <td><a href="${esc(v.url)}" target="_blank" rel="noopener">link</a></td></tr>`).join("") ||
    `<tr><td colspan="7" class="dica">Nenhuma candidatura ainda.</td></tr>`;
}
$("#filtro-realizadas").addEventListener("input", desenharRealizadas);
$("#tabela-realizadas").addEventListener("change", async (e) => {
  if (!e.target.matches("[data-obs]")) return;
  const id = e.target.closest("tr").dataset.id;
  try { await api(`/api/vagas/${id}/candidatura`, { method: "PATCH", body: { observacoes: e.target.value } }); toast("Observação salva"); }
  catch (err) { toast(err.message); }
});

// ---------------------------------------------------------------- Alertas
async function renderAlertas() {
  const vagas = await api("/api/vagas?status=sem_descricao");
  $("#c-alertas").textContent = vagas.length || "";
  $("#lista-alertas").innerHTML = vagas.map((v) => `<div class="item" data-id="${v.id}">
    <div class="cab"><div><b>${esc(v.titulo)}</b> · ${esc(v.empresa)} <small>(${esc(v.fonte)})</small></div>
    <a href="${esc(v.url)}" target="_blank" rel="noopener">Abrir vaga</a></div>
    <textarea rows="4" placeholder="Cole a descrição completa"></textarea>
    <div class="botoes"><button data-acao="analisar">Analisar</button></div></div>`).join("") ||
    `<p class="dica">Nenhum alerta pendente.</p>`;
}
$("#lista-alertas").addEventListener("click", async (e) => {
  if (e.target.dataset.acao !== "analisar") return;
  const item = e.target.closest(".item");
  try {
    const v = await api(`/api/vagas/${item.dataset.id}/descricao`, { method: "POST", body: { descricao: $("textarea", item).value } });
    toast(resultadoTexto(v)); renderAlertas(); carregarPilha();
  } catch (err) { toast(err.message); }
});
$("#form-manual").addEventListener("submit", async (e) => {
  e.preventDefault();
  const corpo = Object.fromEntries(new FormData(e.target));
  try {
    const v = await api("/api/vagas/manual", { method: "POST", body: corpo });
    toast(resultadoTexto(v)); e.target.reset(); carregarPilha();
  } catch (err) { toast(err.message); }
});
function resultadoTexto(v) {
  if (v.status === "compativel") return `Nota ${v.nota}: entrou na pilha`;
  if (v.status === "abaixo_da_nota") return `Nota ${v.nota}: abaixo do corte`;
  if (v.status === "descartada_filtro") return `Descartada: ${v.motivo_descarte}`;
  return `Status: ${v.status}`;
}

// ---------------------------------------------------------------- Recusadas
async function renderRecusadas() {
  const vagas = await api("/api/vagas?status=recusada,abaixo_da_nota,descartada_filtro&limite=150");
  const rotulo = { recusada: "Recusada por você", abaixo_da_nota: "Abaixo da nota", descartada_filtro: "Filtro" };
  $("#lista-recusadas").innerHTML = vagas.map((v) => `<div class="item"><div class="cab">
    <div><b>${esc(v.titulo)}</b> · ${esc(v.empresa)}<br><small>${esc(rotulo[v.status])}${v.motivo_descarte ? ": " + esc(v.motivo_descarte) : ""}</small></div>
    <div>${v.nota ?? ""} · <a href="${esc(v.url)}" target="_blank" rel="noopener">link</a>
    ${v.status === "recusada" ? ` · <button class="link" data-volta="${v.id}">voltar para a pilha</button>` : ""}</div></div></div>`).join("") ||
    `<p class="dica">Nada aqui ainda.</p>`;
}
$("#lista-recusadas").addEventListener("click", async (e) => {
  const id = e.target.dataset.volta;
  if (!id) return;
  try { await api(`/api/vagas/${id}/desfazer`, { method: "POST" }); toast("Voltou para a pilha"); renderRecusadas(); carregarPilha(); }
  catch (err) { toast(err.message); }
});

// ---------------------------------------------------------------- Geral
document.addEventListener("click", async (e) => {
  const id = e.target.dataset?.desc;
  if (!id) return;
  const v = await api(`/api/vagas/${id}`);
  const reqs = (v.analise?.requisitos || []).map((r) => `<li>${esc(r.nome)} (${r.tipo}, peso ${r.peso}): ${esc(r.match.replace("_", " "))}</li>`).join("");
  $("#modal-corpo").innerHTML = `<h3>${esc(v.titulo)} · ${esc(v.empresa)}</h3>${metaVaga(v)}
    ${reqs ? `<h4>Requisitos extraídos (${esc(v.analise.modelo_llm)})</h4><ul>${reqs}</ul>` : ""}<pre>${esc(v.descricao)}</pre>`;
  $("#modal").showModal();
});

document.addEventListener("keydown", (e) => {
  if ($("#aba-pilha").hidden || e.target.matches("input, textarea, select") || $("#modal").open) return;
  if (e.key === "ArrowRight") decidir("confirmar");
  else if (e.key === "ArrowLeft") decidir("recusar");
  else if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); desfazer(); }
});
$("#btn-confirmar").onclick = () => decidir("confirmar");
$("#btn-recusar").onclick = () => decidir("recusar");
$("#btn-desfazer").onclick = desfazer;

const RENDER = { pilha: carregarPilha, candidatar: renderCandidatar, realizadas: renderRealizadas, alertas: renderAlertas, recusadas: renderRecusadas };
$("#abas").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-aba]");
  if (!b) return;
  document.querySelectorAll("#abas button").forEach((x) => x.classList.toggle("ativa", x === b));
  document.querySelectorAll(".aba").forEach((s) => (s.hidden = s.id !== "aba-" + b.dataset.aba));
  RENDER[b.dataset.aba]().catch((err) => toast(err.message));
});

$("#btn-coletar").onclick = async () => {
  const r = await api("/api/coletar", { method: "POST" });
  toast(r.iniciado ? "Buscando vagas em segundo plano…" : r.mensagem);
  $("#btn-coletar").disabled = true;
  const espera = setInterval(async () => {
    const s = await api("/api/resumo");
    if (!s.processando) { clearInterval(espera); $("#btn-coletar").disabled = false; toast("Busca terminada"); carregarPilha(); atualizarContadores(); }
  }, 5000);
};

async function carregarPilha() {
  pilha = await api("/api/vagas?status=compativel");
  renderPilha();
}

async function atualizarContadores() {
  const s = await api("/api/resumo");
  corte = s.nota_corte;
  const c = s.contagem || {};
  $("#c-pilha").textContent = c.compativel || "";
  $("#c-candidatar").textContent = c.em_candidatura || "";
  $("#c-realizadas").textContent = c.candidatada || "";
  $("#c-alertas").textContent = c.sem_descricao || "";
  $("#aviso-perfil").hidden = !s.perfil_exemplo;
  const o = $("#st-ollama");
  o.textContent = s.ollama.ok ? `Ollama: ${s.ollama.modelo}` : "Ollama indisponível (usando heurística)";
  o.title = s.ollama.mensagem;
  o.className = "pill " + (s.ollama.ok ? "ok" : "erro");
}

atualizarContadores().catch((e) => toast(e.message));
carregarPilha().catch((e) => toast(e.message));
