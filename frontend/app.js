/* Opta QuantBet AI — Frontend */

let AUTH_TOKEN = localStorage.getItem("quantbet_token") || "";

function showLoginOverlay(msg = "") {
  const ov = document.getElementById("login-overlay");
  if (!ov) return;
  ov.style.display = "flex";
  const err = document.getElementById("login-error");
  if (err) {
    if (msg) {
      err.textContent = msg;
      err.style.display = "block";
    } else {
      err.style.display = "none";
    }
  }
  const inp = document.getElementById("login-password");
  if (inp) setTimeout(() => inp.focus(), 50);
}

function hideLoginOverlay() {
  const ov = document.getElementById("login-overlay");
  if (ov) ov.style.display = "none";
}

const _originalFetch = window.fetch;
window.fetch = async function (url, options = {}) {
  options = options || {};
  options.headers = options.headers || {};
  if (AUTH_TOKEN) {
    if (typeof options.headers.set === "function") {
      options.headers.set("Authorization", `Bearer ${AUTH_TOKEN}`);
    } else if (Array.isArray(options.headers)) {
      options.headers.push(["Authorization", `Bearer ${AUTH_TOKEN}`]);
    } else {
      options.headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
    }
  }
  const res = await _originalFetch(url, options);
  if (res.status === 401 && typeof url === "string" && url.startsWith("/api/") && !url.includes("/api/auth/")) {
    showLoginOverlay("Sesión expirada o no autorizada. Ingresa tu contraseña.");
  }
  return res;
};

const STATE = {
  meta: null,
  today: null,
  selectedMatch: null,
};

const fmtCOP = (val) => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return "$" + Math.round(Number(val)).toLocaleString("es-CO") + " COP";
};

const fmtPct = (val, digits = 1) => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return (Number(val) * 100).toFixed(digits) + "%";
};

const fmtSignPct = (val, digits = 1) => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  const n = Number(val) * 100;
  return (n >= 0 ? "+" : "") + n.toFixed(digits) + "%";
};

const fmtOdds = (val) => {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return Number(val).toFixed(2);
};

const fmtDateCO = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("es-CO", {
      timeZone: "America/Bogota",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
};

const dateKeyCO = (isoOrDate) => {
  const d = typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate;
  return d.toLocaleDateString("en-CA", { timeZone: "America/Bogota" }); // YYYY-MM-DD
};

const dateLabelCO = (ymd) => {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d, 17, 0, 0));
  return dt.toLocaleDateString("es-CO", {
    timeZone: "America/Bogota",
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
};

function populateDateSelects() {
  if (!STATE.today?.matches) return;
  const todayYMD = dateKeyCO(new Date());
  const tom = new Date(Date.now() + 24 * 3600 * 1000);
  const tomorrowYMD = dateKeyCO(tom);

  const uniqueDates = [...new Set(STATE.today.matches.map((m) => dateKeyCO(m.kickoff)))].sort();

  ["filter-date", "bld-date", "sfb-date", "snba-date"].forEach((id) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    const prev = sel.value || (id === "bld-date" ? "TODAY" : "ALL");
    let html = `
      <option value="ALL">📅 Todas las fechas (${STATE.today.matches.length})</option>
      <option value="TODAY">⚡ Solo Hoy (${dateLabelCO(todayYMD)})</option>
      <option value="TOMORROW">⏭️ Solo Mañana (${dateLabelCO(tomorrowYMD)})</option>
    `;
    uniqueDates.forEach((ymd) => {
      const tag = ymd === todayYMD ? " — HOY" : ymd === tomorrowYMD ? " — MAÑANA" : "";
      html += `<option value="${ymd}">📆 ${dateLabelCO(ymd)}${tag}</option>`;
    });
    sel.innerHTML = html;
    if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
  });
}

function matchPassesDateFilter(m, filterVal) {
  if (!filterVal || filterVal === "ALL") return true;
  const mYMD = dateKeyCO(m.kickoff);
  if (filterVal === "TODAY") return mYMD === dateKeyCO(new Date());
  if (filterVal === "TOMORROW") return mYMD === dateKeyCO(new Date(Date.now() + 24 * 3600 * 1000));
  return mYMD === filterVal;
}

const badgeHTML = (label) => {
  if (label === "VALUE") return `<span class="badge badge-value">💎 VALUE</span>`;
  if (label === "MARGINAL") return `<span class="badge badge-marginal">⚠️ MARGINAL</span>`;
  return `<span class="badge badge-nobet">${label || "NO BET"}</span>`;
};

// ---------------------------------------------------------------------------
// Construcción del reporte ejecutivo 📌📊⚖️💎🎯🛡️⚠️
// ---------------------------------------------------------------------------
function renderOptaExecutiveReport(m, allowSavePick = true) {
  const bp = m.best_pick || m.selections?.[0] || {};
  const leagueName = m.league ? `${m.league.flag} ${m.league.name}` : m.div;
  const scoreBadge = m.final_score ? ` · Marcador Final: <strong>${m.final_score}</strong>` : "";

  const insightsList = (m.insights || []).map((x) => `<li>${x}</li>`).join("");
  const risksList = (m.risks || []).map((x) => `<li>${x}</li>`).join("");

  // Tabla de todos los mercados
  const selRows = (m.selections || [])
    .map((s) => {
      const saveBtn =
        allowSavePick && s.odds
          ? `<button class="btn btn-ghost btn-save-pick" style="padding:4px 8px;font-size:11px" data-key="${s.key}">+ Registrar</button>`
          : "";
      return `
      <tr>
        <td><strong>${s.market_name}</strong> · ${s.name}</td>
        <td class="mono">${fmtOdds(s.odds)}</td>
        <td class="mono">${fmtPct(s.p_market)}</td>
        <td class="mono">${fmtPct(s.p_model)}</td>
        <td class="mono"><strong>${fmtPct(s.p_real)}</strong></td>
        <td class="mono">${fmtOdds(s.fair_odds)}</td>
        <td class="mono" style="color:${(s.ev || 0) >= 0.03 ? "#10b981" : (s.ev || 0) > 0 ? "#f59e0b" : "#94a3b8"}">
          <strong>${fmtSignPct(s.ev)}</strong>
        </td>
        <td>${badgeHTML(s.label)}</td>
        <td class="mono">${s.stake_pct > 0 ? fmtPct(s.stake_pct, 2) + " (" + fmtCOP(s.stake_amount) + ")" : "0%"}</td>
        <td>${saveBtn}</td>
      </tr>`;
    })
    .join("");

  // Matriz Poisson 6x6 (solo para fútbol)
  let matrixSectionHTML = "";
  if (m.matrix && m.matrix.length) {
    let matrixHTML = `<div class="matrix-grid"><div class="matrix-cell"><strong>L \\ V</strong></div>`;
    for (let j = 0; j < 6; j++) matrixHTML += `<div class="matrix-cell"><strong>${j}</strong></div>`;
    (m.matrix || []).forEach((row, i) => {
      matrixHTML += `<div class="matrix-cell"><strong>${i}</strong></div>`;
      row.forEach((p) => {
        const alpha = Math.min(p * 5.2, 0.75).toFixed(2);
        matrixHTML += `<div class="matrix-cell" style="background:rgba(16,185,129,${alpha})">${(p * 100).toFixed(1)}%</div>`;
      });
    });
    matrixHTML += `</div>`;
    matrixSectionHTML = `
      <div class="opta-block">
        <h4>🎲 MATRIZ DE MARCADORES EXACTOS (DIXON-COLES POISSON 0–5 GOLES)</h4>
        ${matrixHTML}
      </div>`;
  }

  const minBetNote = bp.below_min_bet
    ? ` <span style="color:#f59e0b">(Nota: el stake matemático de ${fmtCOP(bp.stake_amount)} es inferior a la apuesta mínima configurada de tu casa)</span>`
    : "";
  const wplayLink = m.wplay_url
    ? ` · <a href="${m.wplay_url}" target="_blank" rel="noopener" style="color:#10b981;font-weight:700;text-decoration:underline">🔗 Abrir partido directo en Wplay.co ↗</a>`
    : "";

  return `
    <div class="opta-report">
      <div class="opta-block">
        <h4>📌 ENCUENTRO / EVENTO</h4>
        <p style="font-size:16px;font-weight:700">${m.home} vs ${m.away} — ${leagueName}</p>
        <p style="font-size:12.5px;color:#94a3b8">
          Fecha (Colombia): ${fmtDateCO(m.kickoff)} · Muestra evaluada: ${m.sample} partidos · Fuente: <strong>${m.odds_source || "—"}</strong>${wplayLink}${scoreBadge}
        </p>
      </div>

      <div class="opta-block">
        <h4>📊 RESUMEN DE MÉTRICAS OPTA / xG (INPUT)</h4>
        <ul>${insightsList}</ul>
      </div>

      <div class="opta-block">
        <h4>⚖️ ANÁLISIS DE PROBABILIDAD (SELECCIÓN PRINCIPAL: ${bp.name || "—"})</h4>
        <ul>
          <li><strong>Cuota ofrecida:</strong> <span class="mono">${fmtOdds(bp.odds)}</span> (${bp.odds_source || "Mercado"}) → Implícita bruta: <span class="mono">${fmtPct(bp.p_implied_raw)}</span> | De-vig (sin margen casa): <span class="mono">${fmtPct(bp.p_market)}</span></li>
          <li><strong>Probabilidad Modelo Poisson Dixon-Coles (xG):</strong> <span class="mono">${fmtPct(bp.p_model)}</span></li>
          <li><strong>Probabilidad Real (Consenso Modelo + Mercado):</strong> <span class="mono"><strong>${fmtPct(bp.p_real)}</strong></span> (Cuota justa: <span class="mono">${fmtOdds(bp.fair_odds)}</span>)</li>
        </ul>
      </div>

      <div class="opta-block">
        <h4>💎 EVALUACIÓN DE VALOR (+EV)</h4>
        <p style="font-size:14px">
          EV Matemático: <strong class="mono" style="color:${(bp.ev || 0) >= 0.03 ? "#10b981" : "#f59e0b"}">${fmtSignPct(bp.ev, 2)}</strong>
          · Edge sobre probabilidad sin vig: <strong class="mono">${fmtSignPct(bp.edge, 2)}</strong>
          · Clasificación: ${badgeHTML(bp.label)}
        </p>
      </div>

      <div class="opta-block">
        <h4>🎯 SELECCIÓN RECOMENDADA</h4>
        <p style="font-size:15px;font-weight:700">
          ${bp.label === "VALUE" ? `✅ APOSTAR: ${bp.market_name} → ${bp.name} @ ${fmtOdds(bp.odds)}` : `⛔ NO APOSTAR (${bp.name || "Sin valor suficiente"} tiene EV ${fmtSignPct(bp.ev)} — inferior al umbral requerido)`}
        </p>
      </div>

      <div class="opta-block">
        <h4>🛡️ STAKE &amp; GESTIÓN DE RIESGO (CRITERIO DE KELLY FRACCIONAL)</h4>
        <p style="font-size:13.5px">
          Stake Óptimo: <strong class="mono">${fmtPct(bp.stake_pct, 2)}</strong> del Bankroll
          (<strong>${fmtCOP(bp.stake_amount)}</strong>) · Nivel de confianza: <strong>${bp.confidence || "—"}</strong>
          (Factor estabilidad muestra: ${(bp.confidence_factor || 1) * 100}%)${minBetNote}
        </p>
      </div>

      <div class="opta-block">
        <h4>⚠️ VARIABLES DE VARIANZA / RIESGO</h4>
        <ul>${risksList}</ul>
      </div>

      <div class="opta-block">
        <h4>📋 COMPARATIVA DE TODOS LOS MERCADOS DEL PARTIDO</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Mercado / Selección</th>
                <th>Cuota</th>
                <th>P_DeVig</th>
                <th>P_Modelo</th>
                <th>P_Real</th>
                <th>Cuota Justa</th>
                <th>+EV</th>
                <th>Señal</th>
                <th>Stake</th>
                <th></th>
              </tr>
            </thead>
            <tbody>${selRows}</tbody>
          </table>
        </div>
      </div>

      ${renderFootballOptaPropsHTML(m)}
      ${renderNBAPropsAndBreakdownHTML(m)}
      ${matrixSectionHTML}
    </div>
  `;
}

function renderFootballOptaPropsHTML(m) {
  const p = m.opta_props;
  if (!p) return "";
  const c = p.corners || {};
  const s = p.sot || {};
  const f = p.fouls || {};
  const k = p.cards || {};
  return `
    <div class="opta-block">
      <h4>🚩 MÉTRICAS ESPECIALES OPTA FÚTBOL (TIROS AL ARCO, CÓRNERS, FALTAS Y TARJETAS)</h4>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Métrica Opta</th>
              <th>Proyección ${m.home}</th>
              <th>Proyección ${m.away}</th>
              <th>Total Esperado (λ)</th>
              <th>Probabilidades de Línea (Poisson)</th>
              <th>Cuotas Justas</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>🎯 Tiros al Arco (SOT)</strong></td>
              <td class="mono">${s.home}</td>
              <td class="mono">${s.away}</td>
              <td class="mono"><strong style="color:#10b981">${s.total} tiros a puerta</strong></td>
              <td class="mono">
                Más de 7.5: <strong>${fmtPct(s.p_over_75)}</strong> ·
                Más de 8.5: <strong>${fmtPct(s.p_over_85)}</strong> ·
                Más de 9.5: <strong>${fmtPct(s.p_over_95)}</strong>
              </td>
              <td class="mono">
                O7.5 @ ${fmtOdds(1 / Math.max(s.p_over_75, 0.01))} |
                O8.5 @ ${fmtOdds(1 / Math.max(s.p_over_85, 0.01))}
              </td>
            </tr>
            <tr>
              <td><strong>🚩 Tiros de Esquina (Córners)</strong></td>
              <td class="mono">${c.home}</td>
              <td class="mono">${c.away}</td>
              <td class="mono"><strong style="color:#10b981">${c.total} córners</strong></td>
              <td class="mono">
                Más de 8.5: <strong>${fmtPct(c.p_over_85)}</strong> ·
                Más de 9.5: <strong>${fmtPct(c.p_over_95)}</strong> ·
                Más de 10.5: <strong>${fmtPct(c.p_over_105)}</strong>
              </td>
              <td class="mono">
                O8.5 @ ${fmtOdds(1 / Math.max(c.p_over_85, 0.01))} |
                O9.5 @ ${fmtOdds(1 / Math.max(c.p_over_95, 0.01))}
              </td>
            </tr>
            <tr>
              <td><strong>🛑 Sección de Faltas Cometidas</strong></td>
              <td class="mono">${f.home}</td>
              <td class="mono">${f.away}</td>
              <td class="mono"><strong style="color:#f59e0b">${f.total} faltas</strong></td>
              <td class="mono">
                Más de 21.5: <strong>${fmtPct(f.p_over_215)}</strong> ·
                Más de 23.5: <strong>${fmtPct(f.p_over_235)}</strong> ·
                Más de 25.5: <strong>${fmtPct(f.p_over_255)}</strong>
              </td>
              <td class="mono">
                O21.5 @ ${fmtOdds(1 / Math.max(f.p_over_215, 0.01))} |
                O23.5 @ ${fmtOdds(1 / Math.max(f.p_over_235, 0.01))}
              </td>
            </tr>
            <tr>
              <td><strong>🟨 Tarjetas Disciplinarias</strong></td>
              <td class="mono">${k.home}</td>
              <td class="mono">${k.away}</td>
              <td class="mono"><strong>${k.total} tarjetas</strong></td>
              <td class="mono">
                Más de 3.5: <strong>${fmtPct(k.p_over_35)}</strong> ·
                Más de 4.5: <strong>${fmtPct(k.p_over_45)}</strong>
              </td>
              <td class="mono">
                O3.5 @ ${fmtOdds(1 / Math.max(k.p_over_35, 0.01))} |
                O4.5 @ ${fmtOdds(1 / Math.max(k.p_over_45, 0.01))}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderNBAPropsAndBreakdownHTML(m) {
  if (m.div !== "NBA") return "";
  const bd = m.nba_breakdown || {};
  const props = m.player_props || [];

  let bdHTML = "";
  if (bd.home && bd.away) {
    bdHTML = `
      <div class="opta-block">
        <h4>🏀 DESGLOSE DE PUNTOS POR EQUIPO, RITMO (PACE) Y MITADES (STATS PERFORM / OPTA)</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Equipo</th>
                <th>Puntos Proyectados (Partido)</th>
                <th>1er Cuarto (Q1)</th>
                <th>1ra Mitad (H1)</th>
                <th>Offensive Rating (ORtg / 100 pos)</th>
                <th>Pace del Partido</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>${bd.home.team} (Local)</strong></td>
                <td class="mono"><strong style="color:#10b981">${bd.home.pts} pts</strong></td>
                <td class="mono">${bd.home.q1} pts</td>
                <td class="mono">${bd.home.h1} pts</td>
                <td class="mono">${bd.home.ortg}</td>
                <td class="mono" rowspan="2" style="vertical-align:middle"><strong>${bd.pace} pos/48m</strong></td>
              </tr>
              <tr>
                <td><strong>${bd.away.team} (Visitante)</strong></td>
                <td class="mono"><strong style="color:#10b981">${bd.away.pts} pts</strong></td>
                <td class="mono">${bd.away.q1} pts</td>
                <td class="mono">${bd.away.h1} pts</td>
                <td class="mono">${bd.away.ortg}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  let propsHTML = "";
  if (props.length) {
    const rows = props
      .map(
        (pp) => `
        <tr>
          <td><span class="badge badge-nobet">${pp.category}</span></td>
          <td><strong>${pp.player}</strong> <span style="color:#94a3b8;font-size:11.5px">(${pp.team})</span></td>
          <td class="mono"><strong>${pp.line}</strong></td>
          <td class="mono" style="color:#67e8f9"><strong>${pp.proj}</strong></td>
          <td class="mono">${fmtOdds(pp.over_odds)} <span style="color:#94a3b8">(${fmtPct(pp.p_over)})</span></td>
          <td class="mono">${fmtOdds(pp.under_odds)} <span style="color:#94a3b8">(${fmtPct(pp.p_under)})</span></td>
          <td><strong style="color:#10b981">${pp.recommended} @ ${fmtOdds(pp.rec_odds)}</strong> (${fmtPct(pp.rec_prob)})</td>
        </tr>`
      )
      .join("");
    propsHTML = `
      <div class="opta-block">
        <h4>⛹️‍♂️ PLAYER PROPS EN VIVO WPLAY.CO (PUNTOS, REBOTES Y ASISTENCIAS POR JUGADOR)</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Categoría</th>
                <th>Jugador</th>
                <th>Línea Wplay</th>
                <th>Proyección Modelo</th>
                <th>Más de (Over)</th>
                <th>Menos de (Under)</th>
                <th>Lado más Probable (Sin Vig)</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }
  return bdHTML + propsHTML;
}

// ---------------------------------------------------------------------------
// Renderizado del Radar del Día
// ---------------------------------------------------------------------------
function renderTodayMatches() {
  const grid = document.getElementById("matches-grid");
  const banner = document.getElementById("round-banner");
  if (!STATE.today) {
    grid.innerHTML = `<div class="card">Cargando partidos y modelos xG...</div>`;
    return;
  }

  if (STATE.today.is_recent_round) {
    banner.classList.remove("hidden");
    banner.innerHTML = `ℹ️ <strong>Ventana de Parón Internacional / Entre Jornadas:</strong> Las 5 grandes ligas europeas no tienen partidos programados en las próximas horas. Se muestra la evaluación cuantitativa completa de la <strong>última jornada disputada</strong>, y puedes usar la pestaña <strong>"🧮 Analizador Manual"</strong> para cotizar cualquier partido futuro con las cuotas de tu casa en Colombia.`;
  } else {
    banner.classList.add("hidden");
  }

  const dateFilter = document.getElementById("filter-date")?.value || "ALL";
  const leagueFilter = document.getElementById("filter-league").value;
  const signalFilter = document.getElementById("filter-signal").value;
  const marketFilter = document.getElementById("filter-market").value;
  const q = document.getElementById("filter-search").value.trim().toLowerCase();
  const qNorm = q
    .replace("brasil", "brazil")
    .replace("singapur", "singapore")
    .replace("japon", "japan")
    .replace("corea", "korea")
    .replace("alemania", "germany")
    .replace("espana", "spain")
    .replace("españa", "spain");

  const matches = (STATE.today.matches || []).filter((m) => {
    if (!matchPassesDateFilter(m, dateFilter)) return false;
    if (leagueFilter === "INTL_ALL" && m.league?.kind !== "intl") return false;
    if (leagueFilter === "CLUB_ALL" && m.league?.kind !== "club") return false;
    if (!["ALL", "INTL_ALL", "CLUB_ALL"].includes(leagueFilter) && m.div !== leagueFilter) return false;
    const text = `${m.home} ${m.away}`.toLowerCase();
    if (q && !text.includes(q) && !text.includes(qNorm)) return false;

    const pick = pickForMarket(m, marketFilter, signalFilter);
    if (!pick) return false;
    if (signalFilter === "SWEET_SPOT") {
      return (pick.p_real || 0) >= 0.525 && (pick.odds || 0) >= 1.72 && (pick.ev || 0) > -0.015;
    }
    if (signalFilter === "HIGH_PROB") {
      return (pick.p_real || 0) >= 0.58 && (pick.odds || 0) >= 1.45;
    }
    if (signalFilter === "VALUE" && pick.label !== "VALUE") return false;
    if (signalFilter === "POSITIVE" && (pick.ev || 0) <= 0) return false;
    return true;
  });

  if ( signalFilter === "SWEET_SPOT" || signalFilter === "HIGH_PROB" ) {
    matches.sort((a, b) => {
      const pa = pickForMarket(a, marketFilter, signalFilter)?.p_real || 0;
      const pb = pickForMarket(b, marketFilter, signalFilter)?.p_real || 0;
      return pb - pa;
    });
  }

  document.getElementById("top-matches").textContent = matches.length;
  document.getElementById("top-value").textContent = matches.filter((m) => m.has_value).length;

  if (!matches.length) {
    grid.innerHTML = `<div class="card">No hay partidos que coincidan con los filtros seleccionados.</div>`;
    return;
  }

  grid.innerHTML = matches
    .map((m) => {
      const pick = pickForMarket(m, marketFilter, signalFilter) || m.best_pick || {};
      const p1x2 = m.probs?.["1x2"] || {};
      const isVal = pick.label === "VALUE";
      const isWplay = (m.odds_source || "").includes("Wplay");
      const isNBA = m.div === "NBA";
      const projLabel = isNBA
        ? `Pts ${m.lambda_home.toFixed(1)} - ${m.lambda_away.toFixed(1)}`
        : `λ ${m.lambda_home.toFixed(2)} - ${m.lambda_away.toFixed(2)}`;
      const fp = m.opta_props;
      const injH = (m.injuries?.home || []).filter(x => /out|doubt|missing|suspend/i.test(`${x.status} ${x.reason || ""}`)).length;
      const injA = (m.injuries?.away || []).filter(x => /out|doubt|missing|suspend/i.test(`${x.status} ${x.reason || ""}`)).length;
      const injBadge = (injH > 0 || injA > 0)
        ? `<div style="font-size:11px;color:#f43f5e;padding:4px 8px;background:rgba(244,63,94,0.08);border-radius:6px;margin-top:4px">
             🏥 <strong>Bajas Confirmadas (Ajustadas):</strong> ${m.home} (${injH}) · ${m.away} (${injA})
           </div>`
        : "";
      const miniPropsHTML = isNBA
        ? `<div style="font-size:11.5px;color:#94a3b8;display:flex;justify-content:space-between;padding:4px 8px;background:rgba(255,255,255,0.02);border-radius:6px">
             <span>⏱️ Pace: <strong>${m.nba_breakdown?.pace ?? "—"}</strong></span>
             <span>🏀 Total Proy: <strong>${(m.lambda_home + m.lambda_away).toFixed(1)} pts</strong></span>
             <span>⛹️ Props: <strong>${(m.player_props || []).length} jugadores</strong></span>
           </div>${injBadge}`
        : (fp
        ? `<div style="font-size:11.5px;color:#94a3b8;display:flex;justify-content:space-between;padding:4px 8px;background:rgba(255,255,255,0.02);border-radius:6px">
             <span>🎯 SOT: <strong>${fp.sot.total}</strong> (${fmtPct(fp.sot.p_over_85, 0)} O8.5)</span>
             <span>🚩 Córners: <strong>${fp.corners.total}</strong> (${fmtPct(fp.corners.p_over_95, 0)} O9.5)</span>
             <span>🛑 Faltas: <strong>${fp.fouls.total}</strong></span>
           </div>`
        : "") + (((!isNBA && (m.profiles?.home?.last5_n || 0) >= 3 && (m.profiles?.away?.last5_n || 0) >= 3))
        ? `<div style="font-size:11px;color:#38bdf8;display:flex;justify-content:space-between;padding:4px 8px;background:rgba(56,189,248,0.06);border-radius:6px;margin-top:4px">
             <span>📊 Últ. 5 Loc: <strong>${m.profiles.home.last5_ov25}/${m.profiles.home.last5_n} +2.5</strong> · ${m.profiles.home.last5_btts}/${m.profiles.home.last5_n} BTTS</span>
             <span>Vis: <strong>${m.profiles.away.last5_ov25}/${m.profiles.away.last5_n} +2.5</strong> · ${m.profiles.away.last5_btts}/${m.profiles.away.last5_n} BTTS</span>
           </div>`
        : "") + injBadge;
      const probBarHTML = isNBA
        ? `<div class="prob-bar" style="grid-template-columns:repeat(2,1fr)">
             <div class="prob-cell">1 Local (${m.home})<strong>${fmtPct(p1x2.H)}</strong></div>
             <div class="prob-cell">2 Visit. (${m.away})<strong>${fmtPct(p1x2.A)}</strong></div>
           </div>`
        : `<div class="prob-bar">
             <div class="prob-cell">1 Local<strong>${fmtPct(p1x2.H)}</strong></div>
             <div class="prob-cell">X Empate<strong>${fmtPct(p1x2.D)}</strong></div>
             <div class="prob-cell">2 Visit.<strong>${fmtPct(p1x2.A)}</strong></div>
           </div>`;
      return `
        <article class="match-card ${isVal ? "value-card" : ""}" data-id="${m.id}">
          <div class="mc-top">
            <span>${m.league?.flag || ""} ${m.league?.name || m.div} ${isWplay ? '<strong style="color:#f59e0b">· Wplay/BetPlay</strong>' : ""}</span>
            <span>${fmtDateCO(m.kickoff)}${m.final_score ? ` · <strong>${m.final_score}</strong>` : ""}</span>
          </div>
          <div class="mc-teams">
            <div class="mc-team-names">${m.home} vs ${m.away}</div>
            <div class="mc-xg-pill">${projLabel}</div>
          </div>
          ${probBarHTML}
          ${miniPropsHTML}
          <div class="mc-pick-box">
            <div>
              <div style="font-size:11px;color:#94a3b8">${pick.market_name || "Mejor opción"}</div>
              <div style="font-weight:700;font-size:13.5px">${pick.name || "—"} @ <span class="mono">${fmtOdds(pick.odds)}</span></div>
              <div style="font-size:11.5px;color:#94a3b8">
                P_Real: <span class="mono">${fmtPct(pick.p_real)}</span> · Stake: <span class="mono">${pick.stake_amount > 0 ? fmtCOP(pick.stake_amount) : "$0"}</span>
              </div>
            </div>
            <div style="text-align:right">
              ${badgeHTML(pick.label)}
              <div class="mono" style="font-size:14px;font-weight:700;margin-top:4px;color:${(pick.ev || 0) >= 0.03 ? "#10b981" : (pick.ev || 0) > 0 ? "#f59e0b" : "#94a3b8"}">
                EV ${fmtSignPct(pick.ev)}
              </div>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  grid.querySelectorAll(".match-card").forEach((card) => {
    card.addEventListener("click", () => {
      const m = STATE.today.matches.find((x) => x.id === card.dataset.id);
      if (m) openMatchModal(m);
    });
  });
}

function pickForMarket(m, marketFilter, signalFilter = "ALL") {
  if (!m.selections) return m.best_pick;
  let sub = m.selections.filter((s) => s.odds !== null && s.odds !== undefined);
  if (marketFilter !== "ALL") {
    sub = sub.filter((s) => s.market === marketFilter);
  }
  if (!sub.length) return marketFilter === "ALL" ? m.best_pick : null;

  if (signalFilter === "SWEET_SPOT") {
    const sweet = sub.filter((s) => (s.p_real || 0) >= 0.525 && (s.odds || 0) >= 1.72 && (s.ev || 0) > -0.015);
    if (!sweet.length) return null;
    // Priorizar el de mayor combinación de probabilidad real + EV
    return sweet.reduce((a, b) => (a.p_real + (a.ev || 0) > b.p_real + (b.ev || 0) ? a : b));
  }
  if (signalFilter === "HIGH_PROB") {
    const hp = sub.filter((s) => (s.p_real || 0) >= 0.58 && (s.odds || 0) >= 1.45);
    if (!hp.length) return null;
    return hp.reduce((a, b) => (a.p_real > b.p_real ? a : b));
  }

  return sub.reduce((a, b) => ((a.ev ?? -99) > (b.ev ?? -99) ? a : b));
}

function openMatchModal(m) {
  STATE.selectedMatch = m;
  const modal = document.getElementById("match-modal");
  const body = document.getElementById("modal-body");
  const injH = m.injuries?.home || [];
  const injA = m.injuries?.away || [];
  const fmtInj = (list) => list.length
    ? list.slice(0, 8).map(x => `<div style="font-size:12px;margin-bottom:3px">• <strong>${x.player}</strong> <span style="color:#f43f5e">[${x.status}]</span> <span style="color:#94a3b8">${x.reason || x.comment || ""}</span></div>`).join("")
    : `<div style="font-size:12px;color:#64748b">Sin bajas reportadas</div>`;
  const injSection = (injH.length || injA.length)
    ? `<div style="background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.3);border-radius:10px;padding:14px;margin-bottom:16px">
         <div style="font-weight:700;font-size:13.5px;color:#f43f5e;margin-bottom:8px">🏥 Parte Médico y Ausencias Confirmadas (Ajustado en el Modelo)</div>
         <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
           <div><div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">${m.home} (${injH.length})</div>${fmtInj(injH)}</div>
           <div><div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">${m.away} (${injA.length})</div>${fmtInj(injA)}</div>
         </div>
       </div>`
    : "";
  body.innerHTML = injSection + renderOptaExecutiveReport(m, true);
  modal.classList.remove("hidden");

  body.querySelectorAll(".btn-save-pick").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const sel = m.selections.find((s) => s.key === btn.dataset.key);
      if (!sel) return;
      await saveManualPick(m, sel);
      btn.textContent = "✓ Guardado";
      btn.disabled = true;
    });
  });
}

async function saveManualPick(m, sel) {
  await fetch("/api/picks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      match_id: m.id,
      div: m.div,
      kickoff: m.kickoff,
      home: m.home,
      away: m.away,
      market: sel.market,
      selection: sel.selection,
      line: sel.line,
      name: sel.name,
      odds: sel.odds,
      p_model: sel.p_model,
      p_market: sel.p_market,
      p_real: sel.p_real,
      stake_pct: sel.stake_pct,
      stake_amount: sel.stake_amount,
      bookmaker: sel.odds_source || "Manual",
    }),
  });
}

// ---------------------------------------------------------------------------
// Pestaña 1A: Apuestas EN VIVO (Tiempo Real desde Wplay.co)
// ---------------------------------------------------------------------------
async function loadLiveEvents() {
  const grid = document.getElementById("live-grid");
  if (!grid) return;
  grid.innerHTML = `<div class="card">🔴 Escaneando partidos EN VIVO en Wplay.co...</div>`;
  try {
    const res = await fetch("/api/live");
    const data = await res.json();
    const evs = data.events || [];
    if (!evs.length) {
      grid.innerHTML = `<div class="card">En este instante no hay partidos en vivo en Fútbol/Baloncesto en Wplay.co. Vuelve a pulsar "🔄 Refrescar En Vivo" más tarde.</div>`;
      return;
    }
    grid.innerHTML = evs
      .map((ev) => {
        const rec = ev.recommended || {};
        const probs = ev.probs || {};
        const probHTML =
          probs.D !== null && probs.D !== undefined
            ? `<div class="prob-bar">
                 <div class="prob-cell">1 (${ev.home})<strong>${fmtPct(probs.H)}</strong><span class="mono" style="font-size:11px;color:#94a3b8">@${fmtOdds(ev.odds.H)}</span></div>
                 <div class="prob-cell">X Empate<strong>${fmtPct(probs.D)}</strong><span class="mono" style="font-size:11px;color:#94a3b8">@${fmtOdds(ev.odds.D)}</span></div>
                 <div class="prob-cell">2 (${ev.away})<strong>${fmtPct(probs.A)}</strong><span class="mono" style="font-size:11px;color:#94a3b8">@${fmtOdds(ev.odds.A)}</span></div>
               </div>`
            : `<div class="prob-bar" style="grid-template-columns:repeat(2,1fr)">
                 <div class="prob-cell">1 (${ev.home})<strong>${fmtPct(probs.H)}</strong><span class="mono" style="font-size:11px;color:#94a3b8">@${fmtOdds(ev.odds.H)}</span></div>
                 <div class="prob-cell">2 (${ev.away})<strong>${fmtPct(probs.A)}</strong><span class="mono" style="font-size:11px;color:#94a3b8">@${fmtOdds(ev.odds.A)}</span></div>
               </div>`;
        return `
          <article class="match-card value-card" style="border-color:rgba(244,63,94,0.6)">
            <div class="mc-top">
              <span style="color:#f43f5e;font-weight:700">🔴 EN VIVO · ${ev.sport}</span>
              <span class="mono" style="color:#cbd5e1">${ev.clock} ${ev.period ? `(${ev.period})` : ""}</span>
            </div>
            <div class="mc-teams">
              <div class="mc-team-names">${ev.home} <strong style="color:#10b981;margin:0 6px">${ev.score}</strong> ${ev.away}</div>
            </div>
            ${probHTML}
            <div class="mc-pick-box">
              <div>
                <div style="font-size:11px;color:#94a3b8">Lado más probable en vivo (Sin Vig)</div>
                <div style="font-weight:700;font-size:13.5px">${rec.name} @ <span class="mono">${fmtOdds(rec.odds)}</span></div>
                <div style="font-size:11.5px;color:#94a3b8">Prob. Real: <strong class="mono" style="color:#10b981">${fmtPct(rec.prob)}</strong></div>
              </div>
              <div>
                <a href="${ev.wplay_url}" target="_blank" rel="noopener" class="btn btn-primary" style="padding:7px 11px;font-size:12px;text-decoration:none">🔗 Apostar En Vivo ↗</a>
              </div>
            </div>
          </article>
        `;
      })
      .join("");
  } catch (err) {
    grid.innerHTML = `<div class="card" style="color:#f43f5e">Error consultando eventos en vivo: ${err}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Monitor NBA en Vivo: Detector de Sobre-Reacción (+EV In-Play)
// ---------------------------------------------------------------------------
async function loadNbaLiveTracker() {
  const containers = [
    document.getElementById("snba-live-box"),
    document.getElementById("live-nba-box")
  ].filter(Boolean);
  if (!containers.length) return;

  try {
    const res = await fetch("/api/nba/live");
    const data = await res.json();
    const liveMatches = data.live_matches || [];

    let html = "";
    if (liveMatches.length > 0) {
      html = `
        <div class="card" style="border: 1px solid rgba(244, 63, 94, 0.4); background: linear-gradient(180deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%); margin-bottom: 20px;">
          <div class="card-header-flex" style="margin-bottom: 14px;">
            <div>
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <span class="badge" style="background:#ef4444;color:#fff;animation:pulse 2s infinite">🔴 ${liveMatches.length} EN VIVO AHORA</span>
                <h2 class="card-title" style="margin:0;font-size:18px">🏀 Monitor NBA en Vivo: Detector de Sobre-Reacción (+EV In-Play)</h2>
              </div>
              <p class="card-desc" style="margin:0;font-size:12.5px;color:#94a3b8">
                Compara posesión a posesión el ritmo real (Pace) contra las proyecciones cuantitativas. Detecta líneas infladas por euforia en 1Q/2Q y oportunidades de hándicap con colchón de seguridad.
              </p>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(360px, 1fr));gap:16px">
            ${liveMatches.map(m => {
              const qh = m.q_home.map((v, i) => `Q${i+1}: ${v}`).join(" | ");
              const qa = m.q_away.map((v, i) => `Q${i+1}: ${v}`).join(" | ");
              const paceColor = m.pace_badge === "overheated" ? "#f43f5e" : m.pace_badge === "cold" ? "#38bdf8" : "#10b981";
              
              const signalsHTML = (m.signals || []).map(s => `
                <div style="background:rgba(15, 23, 42, 0.7);border:1px solid rgba(56, 189, 248, 0.3);border-radius:8px;padding:12px;margin-top:10px">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <span style="font-size:11px;font-weight:700;color:#38bdf8;text-transform:uppercase;letter-spacing:0.5px">${s.badge}</span>
                    <span style="font-size:12px;font-weight:700;color:#10b981;background:rgba(16,185,129,0.15);padding:2px 8px;border-radius:4px">EV: ${s.ev}</span>
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <strong style="font-size:15px;color:#fff">${s.titulo}</strong>
                    <span class="mono" style="font-size:14px;color:#facc15;font-weight:700">@${s.cuota_aprox.toFixed(2)}</span>
                  </div>
                  <div style="font-size:11.5px;color:#94a3b8;line-height:1.4;margin-bottom:8px">
                    💡 ${s.razon}
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-size:11px;color:#64748b">Prob. Real: <strong style="color:#e2e8f0">${(s.prob_real * 100).toFixed(1)}%</strong></span>
                    <a href="https://wplay.co/apuestas/baloncesto/estados-unidos/nba" target="_blank" rel="noopener" class="btn btn-primary" style="padding:4px 10px;font-size:11.5px;text-decoration:none">
                      🚀 Apostar en Wplay ↗
                    </a>
                  </div>
                </div>
              `).join("");

              return `
                <div class="match-card" style="background:rgba(30, 41, 59, 0.6);border:1px solid rgba(148, 163, 184, 0.2);border-radius:10px;padding:16px">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                    <span style="font-size:12px;font-weight:700;color:#f43f5e;display:flex;align-items:center;gap:6px">
                      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f43f5e"></span>
                      ${m.status_detail}
                    </span>
                    <span style="font-size:11.5px;color:#94a3b8">Minutos restantes: <strong class="mono" style="color:#e2e8f0">${m.remaining_mins} min</strong></span>
                  </div>

                  <!-- Marcador -->
                  <div style="background:rgba(15, 23, 42, 0.5);border-radius:8px;padding:10px 14px;margin-bottom:12px">
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:15px;margin-bottom:4px">
                      <span>${m.home}</span>
                      <strong class="mono" style="font-size:18px;color:${m.margin >= 0 ? '#10b981' : '#cbd5e1'}">${m.score_home}</strong>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:15px;margin-bottom:8px">
                      <span>${m.away}</span>
                      <strong class="mono" style="font-size:18px;color:${m.margin < 0 ? '#10b981' : '#cbd5e1'}">${m.score_away}</strong>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:11px;color:#64748b;border-top:1px dashed rgba(148,163,184,0.2);padding-top:6px">
                      <span>Total acumulado: <strong style="color:#e2e8f0">${m.total_pts} pts</strong></span>
                      <span>Margen: <strong style="color:#e2e8f0">${Math.abs(m.margin)} pts (${m.margin > 0 ? m.home : m.away})</strong></span>
                    </div>
                  </div>

                  <!-- Desglose por cuartos -->
                  <div style="font-size:11px;color:#94a3b8;margin-bottom:12px;background:rgba(15,23,42,0.3);padding:6px 10px;border-radius:6px">
                    <div><strong>${m.home}:</strong> ${qh || 'En juego'}</div>
                    <div style="margin-top:2px"><strong>${m.away}:</strong> ${qa || 'En juego'}</div>
                  </div>

                  <!-- Termómetro de Ritmo (Pace Meter) -->
                  <div style="background:rgba(15, 23, 42, 0.4);border-radius:8px;padding:10px;margin-bottom:10px;border-left:3px solid ${paceColor}">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                      <span style="font-size:11.5px;color:#94a3b8">Termómetro de Ritmo:</span>
                      <span style="font-size:12px;font-weight:700;color:${paceColor}">${m.pace_status}</span>
                    </div>
                    <div style="font-size:11px;color:#cbd5e1;line-height:1.4">
                      Línea viva estimada: <strong class="mono" style="color:#facc15">${m.live_line_total} pts</strong> 
                      (${m.pace_diff >= 0 ? '+' : ''}${m.pace_diff} pts sobre media). Requieren <strong>${m.req_pts_per_min} pts/min</strong>.
                    </div>
                  </div>

                  <!-- Señales detectadas -->
                  ${signalsHTML || `<div style="font-size:11.5px;color:#64748b;text-align:center;padding:8px">No hay sobre-reacción anómala en este instante (Ritmo dentro de rangos normales).</div>`}
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    } else {
      html = `
        <div class="card" style="border: 1px dashed rgba(148, 163, 184, 0.25); background: rgba(30, 41, 59, 0.3); margin-bottom: 20px; padding: 14px 18px;">
          <div style="display:flex;align-items:center;gap:12px">
            <span style="font-size:24px">🏀</span>
            <div>
              <strong style="color:#e2e8f0;font-size:13.5px">Monitor NBA en Vivo: Detector de Sobre-Reacción (+EV)</strong>
              <div style="font-size:12px;color:#94a3b8;margin-top:2px">
                No hay partidos NBA en juego en este instante. Las alertas automáticas de valor en vivo (Under por ritmo inflado y Hándicaps con colchón) se encenderán en cuanto inicien los partidos de la noche.
              </div>
            </div>
          </div>
        </div>
      `;
    }

    containers.forEach(c => {
      c.innerHTML = html;
    });
  } catch (err) {
    console.warn("Error cargando NBA Live Tracker:", err);
  }
}

// ---------------------------------------------------------------------------
// Pestaña 5B: Analista Cuantitativo Senior (5 Temporadas + Log Loss / Brier)
// ---------------------------------------------------------------------------
async function loadSeniorReport() {
  const out = document.getElementById("senior-report-output");
  if (!out) return;
  out.innerHTML = `<div style="padding:24px;text-align:center;color:#38bdf8">⏳ Ejecutando ingesta de 5 temporadas (football-data.co.uk), validación Walk-Forward y cálculo de Log Loss / Brier / Incertidumbre...</div>`;

  try {
    const res = await fetch("/api/senior-report?include_5y=true");
    const d = await res.json();
    const resExec = (d.resumen_ejecutivo || []).map(l => `<li style="margin-bottom:4px">${l}</li>`).join("");
    const dq = d.datos_calidad || {};
    const mm = d.modelo_metricas || {};
    const h5 = d.hist_5y || {};
    const rows = d.tabla_oportunidades || [];
    const risks = (d.riesgos || []).map(r => `<li style="margin-bottom:4px">${r}</li>`).join("");

    const tableRows = rows.length
      ? rows.map(r => `
          <tr>
            <td><strong>${r.evento}</strong><div style="font-size:11px;color:#94a3b8">${r.liga}</div></td>
            <td><span class="badge" style="background:rgba(56,189,248,0.15);color:#38bdf8">${r.mercado}</span></td>
            <td class="mono">${(r.p_modelo * 100).toFixed(1)}%</td>
            <td class="mono">${(r.p_mercado * 100).toFixed(1)}%</td>
            <td class="mono" style="color:#facc15;font-weight:700">@${r.cuota.toFixed(2)}</td>
            <td class="mono" style="color:#10b981;font-weight:700">+${r.ev_pct.toFixed(1)}%</td>
            <td class="mono" style="color:#cbd5e1">±${r.incertidumbre_pct}%</td>
            <td class="mono" style="font-weight:700">${fmtCOP(r.stake_cop)} <span style="font-size:11px;color:#94a3b8">(${r.stake_pct}%)</span></td>
          </tr>
        `).join("")
      : `<tr><td colspan="8" style="text-align:center;color:#94a3b8;padding:16px">No hay oportunidades que superen el umbral +EV actual en este instante.</td></tr>`;

    out.innerHTML = `
      <div style="display:grid;gap:16px">
        <!-- 1. Resumen Ejecutivo -->
        <div style="background:rgba(15,23,42,0.6);border-left:4px solid #10b981;border-radius:8px;padding:14px 18px">
          <h3 style="margin:0 0 8px;font-size:15px;color:#10b981">1. Resumen Ejecutivo</h3>
          <ul style="margin:0;padding-left:18px;font-size:13px;color:#e2e8f0;line-height:1.5">${resExec}</ul>
        </div>

        <!-- 2 & 3. Datos usados y Métricas del Modelo -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px">
          <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(148,163,184,0.2);border-radius:8px;padding:14px 18px">
            <h3 style="margin:0 0 8px;font-size:15px;color:#38bdf8">2. Datos Usados y su Calidad</h3>
            <div style="font-size:12.5px;color:#cbd5e1;line-height:1.5">
              <div><strong>Muestra histórica 5A:</strong> ${dq.muestra_5y || "—"}</div>
              <div style="margin-top:4px"><strong>Con cuotas de cierre:</strong> ${(h5.matches_with_odds || 0).toLocaleString("es-CO")} partidos</div>
              <div style="margin-top:4px"><strong>Calidad:</strong> ${dq.calidad || ""}</div>
              <ul style="margin:8px 0 0;padding-left:18px;color:#94a3b8;font-size:12px">
                ${(dq.fuentes || []).map(f => `<li>${f}</li>`).join("")}
              </ul>
            </div>
          </div>

          <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(148,163,184,0.2);border-radius:8px;padding:14px 18px">
            <h3 style="margin:0 0 8px;font-size:15px;color:#a855f7">3. Modelo, Calibración y Riesgo</h3>
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-size:12.5px">
              <div style="background:rgba(30,41,59,0.6);padding:8px;border-radius:6px">
                <div style="font-size:11px;color:#94a3b8">Log Loss 5A (Mercado)</div>
                <strong class="mono" style="font-size:15px;color:#fff">${mm.log_loss_5y_mercado ?? "—"}</strong>
              </div>
              <div style="background:rgba(30,41,59,0.6);padding:8px;border-radius:6px">
                <div style="font-size:11px;color:#94a3b8">Brier Score (Modelo vs Mkt)</div>
                <strong class="mono" style="font-size:15px;color:#10b981">${mm.brier_modelo ?? "—"} <span style="font-size:11px;color:#94a3b8">vs ${mm.brier_mercado ?? "—"}</span></strong>
              </div>
              <div style="background:rgba(30,41,59,0.6);padding:8px;border-radius:6px">
                <div style="font-size:11px;color:#94a3b8">Max Drawdown (Backtest)</div>
                <strong class="mono" style="font-size:15px;color:#f43f5e">${mm.max_drawdown_pct ?? 0}%</strong>
              </div>
              <div style="background:rgba(30,41,59,0.6);padding:8px;border-radius:6px">
                <div style="font-size:11px;color:#94a3b8">Sharpe Ratio / ROI</div>
                <strong class="mono" style="font-size:15px;color:#38bdf8">${mm.sharpe_ratio ?? 0} / ${mm.roi_backtest_pct ?? 0}%</strong>
              </div>
            </div>
            <div style="font-size:11.5px;color:#94a3b8;margin-top:8px"><strong>Validación:</strong> ${mm.validacion || ""}</div>
          </div>
        </div>

        <!-- 4. Tabla de Oportunidades -->
        <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(148,163,184,0.2);border-radius:8px;padding:14px 18px">
          <h3 style="margin:0 0 10px;font-size:15px;color:#facc15">4. Oportunidades +EV con Incertidumbre Bayesiana</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Evento</th>
                  <th>Mercado</th>
                  <th>P modelo</th>
                  <th>P mercado</th>
                  <th>Cuota</th>
                  <th>EV%</th>
                  <th>Incertidumbre (IC 95%)</th>
                  <th>Stake (Kelly)</th>
                </tr>
              </thead>
              <tbody>${tableRows}</tbody>
            </table>
          </div>
        </div>

        <!-- 5. Riesgos y qué podría invalidar el análisis -->
        <div style="background:rgba(244,63,94,0.08);border:1px solid rgba(244,63,94,0.3);border-radius:8px;padding:14px 18px">
          <h3 style="margin:0 0 8px;font-size:15px;color:#f43f5e">5. Riesgos y Qué Podría Invalidar el Análisis</h3>
          <ul style="margin:0;padding-left:18px;font-size:12.5px;color:#cbd5e1;line-height:1.5">${risks}</ul>
        </div>

        <!-- 6. Aviso de Responsabilidad -->
        <div style="background:rgba(30,41,59,0.5);border-radius:8px;padding:10px 14px;font-size:12px;color:#94a3b8;text-align:center">
          ⚠️ ${d.aviso_responsable}
        </div>
      </div>
    `;
  } catch (err) {
    out.innerHTML = `<div style="color:#f43f5e;padding:16px">Error generando reporte Senior: ${err}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Pestaña 1B: Armador Automático de Boleto Wplay (1-Clic)
// ---------------------------------------------------------------------------
function wplayInstruction(m, sel) {
  if (sel.market === "1x2") {
    const btnName = sel.selection === "H" ? m.home : sel.selection === "A" ? m.away : "Empate";
    return `Mercado <strong>"Resultado Tiempo Completo"</strong> → Botón <strong>"${btnName}"</strong>`;
  }
  if (sel.market === "btts") {
    const btnName = sel.selection === "Y" ? "Si" : "No";
    return `Mercado <strong>"Ambos Equipos Anotan"</strong> → Botón <strong>"${btnName}"</strong>`;
  }
  if (sel.market === "ou25") {
    const side = sel.selection === "O" ? "Más de" : "Menos de";
    return `Mercado <strong>"Total Goles Más/Menos de"</strong> → Columna <strong>"${side} 2.5"</strong>`;
  }
  if (sel.market === "ah") {
    return `Mercado <strong>"Handicap Asiático"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "moneyline") {
    return `Mercado NBA <strong>"Lineas del Juego → Ganará"</strong> → Botón <strong>"${sel.name.replace("Gana ", "")}"</strong>`;
  }
  if (sel.market === "spread") {
    return `Mercado NBA <strong>"Lineas del Juego → Handicap"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "total") {
    return `Mercado NBA <strong>"Lineas del Juego → Totales"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "fb_corners") {
    return `Mercado <strong>"Tiros de Esquina Más/Menos"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "fb_sot") {
    return `Mercado <strong>"Tiros a Puerta / Crear Apuesta"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "fb_fouls") {
    return `Mercado <strong>"Faltas del Partido"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "fb_cards") {
    return `Mercado <strong>"Total de Tarjetas"</strong> → Botón <strong>"${sel.name}"</strong>`;
  }
  if (sel.market === "nba_prop") {
    return `Mercado NBA <strong>"${sel.market_name}"</strong> → Jugador <strong>"${sel.name}"</strong>`;
  }
  return sel.name;
}

function buildMatchPoolForBuilder(m, mktFilter) {
  const pool = [];
  const isNBA = m.div === "NBA";

  // 1. Mercados principales (Fútbol 1x2/ou25/btts/ah o NBA moneyline/spread/total)
  if (mktFilter === "ALL" || (mktFilter === "MAIN_FB" && !isNBA) || (mktFilter === "NBA_MAIN" && isNBA)) {
    for (const s of m.selections || []) {
      if (s.odds && s.odds >= 1.25 && s.odds <= 2.75) {
        pool.push(s);
      }
    }
  } else if (mktFilter === "FB_GOALS_BTTS" && !isNBA) {
    for (const s of m.selections || []) {
      if (s.market === "ou25" || s.market === "btts") {
        const effOdds = s.odds || (s.p_real >= 0.52 ? +(0.94 / s.p_real).toFixed(2) : null);
        if (effOdds && effOdds >= 1.22 && effOdds <= 2.75) {
          pool.push({
            ...s,
            odds: effOdds,
            ev: s.ev !== null && s.ev !== undefined ? s.ev : (s.p_real * effOdds - 1.0),
          });
        }
      }
    }
  }

  // 2. Especiales de Fútbol Opta (Córners, SOT, Faltas, Tarjetas)
  if (!isNBA && m.opta_props) {
    const p = m.opta_props;
    const synth = (mktKey, mktTitle, label, prob) => {
      // Cuota estándar de mercado en Wplay con ~5.5% de margen sobre línea principal (~1.83 - 1.90)
      const estOdds = Math.min(2.25, Math.max(1.45, +(0.945 / Math.max(prob, 0.35)).toFixed(2)));
      const ev = prob * 1.85 - 1.0;
      return {
        market: mktKey,
        market_name: mktTitle,
        name: label,
        odds: 1.85,
        p_real: prob,
        ev: ev,
      };
    };

    if (mktFilter === "ALL" || mktFilter === "FB_CORNERS") {
      const pO85 = p.corners.p_over_85;
      const pU105 = 1 - p.corners.p_over_105;
      pool.push(
        pO85 >= pU105
          ? synth("fb_corners", "🚩 Córners", `Más de 8.5 Córners (Proy: ${p.corners.total})`, pO85)
          : synth("fb_corners", "🚩 Córners", `Menos de 10.5 Córners (Proy: ${p.corners.total})`, pU105)
      );
    }
    if (mktFilter === "ALL" || mktFilter === "FB_SOT") {
      const pO75 = p.sot.p_over_75;
      const pU95 = 1 - p.sot.p_over_95;
      pool.push(
        pO75 >= pU95
          ? synth("fb_sot", "🎯 Tiros al Arco (SOT)", `Más de 7.5 Tiros al Arco (Proy: ${p.sot.total})`, pO75)
          : synth("fb_sot", "🎯 Tiros al Arco (SOT)", `Menos de 9.5 Tiros al Arco (Proy: ${p.sot.total})`, pU95)
      );
    }
    if (mktFilter === "ALL" || mktFilter === "FB_FOULS") {
      const pO215 = p.fouls.p_over_215;
      const pU235 = 1 - p.fouls.p_over_235;
      pool.push(
        pO215 >= pU235
          ? synth("fb_fouls", "🛑 Sección de Faltas", `Más de 21.5 Faltas (Proy: ${p.fouls.total})`, pO215)
          : synth("fb_fouls", "🛑 Sección de Faltas", `Menos de 23.5 Faltas (Proy: ${p.fouls.total})`, pU235)
      );
    }
    if (mktFilter === "ALL" || mktFilter === "FB_CARDS") {
      const pO35 = p.cards.p_over_35;
      const pU45 = 1 - p.cards.p_over_45;
      pool.push(
        pO35 >= pU45
          ? synth("fb_cards", "🟨 Tarjetas Disciplinarias", `Más de 3.5 Tarjetas (Proy: ${p.cards.total})`, pO35)
          : synth("fb_cards", "🟨 Tarjetas Disciplinarias", `Menos de 4.5 Tarjetas (Proy: ${p.cards.total})`, pU45)
      );
    }
  }

  // 3. Player Props NBA verificados en Wplay.co (Puntos, Rebotes, Asistencias por jugador)
  if (isNBA && m.player_props?.length) {
    const catMap = { NBA_PTS: "Puntos", NBA_REB: "Rebotes", NBA_AST: "Asistencias" };
    const targetCat = catMap[mktFilter];
    for (const pp of m.player_props) {
      if (targetCat && pp.category !== targetCat) continue;
      if (mktFilter === "ALL" || targetCat) {
        pool.push({
          market: "nba_prop",
          market_name: `${pp.category} totales de jugador`,
          name: `${pp.player}: ${pp.recommended} ${pp.category} (Proy: ${pp.proj})`,
          odds: pp.rec_odds,
          p_real: pp.rec_prob,
          ev: pp.rec_prob * pp.rec_odds - 1.0,
        });
      }
    }
  }

  return pool;
}

function renderWplayBuilder() {
  const out = document.getElementById("builder-output");
  if (!out || !STATE.today) return;

  const dateFilter = document.getElementById("bld-date")?.value || "TODAY";
  const mktFilter = document.getElementById("bld-market")?.value || "ALL";
  const mode = document.getElementById("bld-mode").value;
  const nLegs = parseInt(document.getElementById("bld-legs").value, 10) || 2;
  const stake = parseFloat(document.getElementById("bld-stake").value) || 29000;

  let dateBannerNote = "";

  function collectCandidates(dFilter, relaxed = false) {
    const list = [];
    for (const m of STATE.today.matches || []) {
      if (!matchPassesDateFilter(m, dFilter)) continue;
      let valid = buildMatchPoolForBuilder(m, mktFilter);
      if (!valid.length) continue;

      if (mode === "SAFE") {
        const minP = relaxed ? 0.50 : 0.57;
        const filtered = valid.filter((s) => (s.p_real || 0) >= minP);
        if (filtered.length) valid = filtered;
        valid.sort((a, b) => (b.p_real + (b.ev || 0) * 0.4) - (a.p_real + (a.ev || 0) * 0.4));
      } else if (mode === "SWEET") {
        const minP = relaxed ? 0.50 : 0.525;
        const filtered = valid.filter((s) => (s.p_real || 0) >= minP && s.odds >= 1.50);
        if (filtered.length) valid = filtered;
        valid.sort((a, b) => (b.p_real + (b.ev || 0)) - (a.p_real + (a.ev || 0)));
      } else {
        const minEv = relaxed ? -0.05 : 0.01;
        const filtered = valid.filter((s) => (s.ev || 0) >= minEv && (s.p_real || 0) >= 0.44);
        if (filtered.length) valid = filtered;
        valid.sort((a, b) => (b.ev || 0) - (a.ev || 0));
      }

      if (valid.length) {
        list.push({ match: m, sel: valid[0] });
      }
    }
    return list;
  }

  let candidates = collectCandidates(dateFilter, false);
  if (candidates.length < nLegs) {
    candidates = collectCandidates(dateFilter, true);
  }
  if (candidates.length < nLegs && dateFilter !== "ALL") {
    dateBannerNote = `<div class="alert-banner" style="margin-bottom:12px">ℹ️ Para la fecha seleccionada no había suficientes partidos de ese mercado específico (por ejemplo, hoy miércoles hay 12 juegos de NBA y el fútbol regresa el viernes 20 de nov). Se muestran las mejores selecciones de las fechas más cercanas.</div>`;
    candidates = collectCandidates("ALL", true);
  }

  if (mode === "SAFE") {
    candidates.sort((a, b) => (b.sel.p_real + (b.sel.ev || 0) * 0.6) - (a.sel.p_real + (a.sel.ev || 0) * 0.6));
  } else if (mode === "SWEET") {
    candidates.sort((a, b) => (b.sel.p_real + (b.sel.ev || 0)) - (a.sel.p_real + (a.sel.ev || 0)));
  } else {
    candidates.sort((a, b) => (b.sel.ev || 0) - (a.sel.ev || 0));
  }

  const chosen = candidates.slice(0, nLegs);
  if (!chosen.length) {
    out.innerHTML = `<div class="opta-block">No se encontraron suficientes selecciones para este filtro. Prueba cambiando a "📅 Toda la Semana".</div>`;
    return;
  }

  const totalOdds = chosen.reduce((acc, x) => acc * x.sel.odds, 1.0);
  const combinedProb = chosen.reduce((acc, x) => acc * x.sel.p_real, 1.0);
  const combinedEV = combinedProb * totalOdds - 1.0;
  const potentialReturn = stake * totalOdds;
  const netProfit = potentialReturn - stake;

  const legsHTML = chosen
    .map((item, idx) => {
      const m = item.match;
      const s = item.sel;
      return `
        <div class="opta-block" style="display:flex;justify-content:space-between;align-items:center;gap:16px">
          <div>
            <div style="font-size:12px;color:#94a3b8">
              <strong>PATA #${idx + 1}</strong> · ${m.league?.flag || ""} ${m.league?.name || m.div} · ${fmtDateCO(m.kickoff)}
            </div>
            <div style="font-size:16px;font-weight:700;margin:3px 0">${m.home} vs ${m.away}</div>
            <div style="font-size:13.5px;color:#e2e8f0">
              👉 En Wplay toca: ${wplayInstruction(m, s)}
            </div>
            <div style="font-size:12px;color:#94a3b8;margin-top:4px">
              Probabilidad Real: <strong class="mono" style="color:#10b981">${fmtPct(s.p_real)}</strong> ·
              Valor Individual: <strong class="mono">${fmtSignPct(s.ev)}</strong>
            </div>
          </div>
          <div style="text-align:right;min-width:190px">
            <div class="mono" style="font-size:20px;font-weight:800;color:#10b981">@ ${fmtOdds(s.odds)}</div>
            ${
              m.wplay_url
                ? `<a href="${m.wplay_url}" target="_blank" rel="noopener" class="btn btn-primary" style="display:inline-block;margin-top:8px;text-decoration:none;padding:7px 12px;font-size:12.5px">🔗 Abrir en Wplay.co ↗</a>`
                : ""
            }
          </div>
        </div>
      `;
    })
    .join("");

  out.innerHTML = `
    ${dateBannerNote}
    <div class="kpi-grid" style="margin-bottom:16px">
      <div class="kpi-box"><div class="k-label">Cuota Total Wplay.co</div><div class="k-val" style="color:#10b981">${totalOdds.toFixed(2)}</div></div>
      <div class="kpi-box"><div class="k-label">Probabilidad Real Combinada</div><div class="k-val">${fmtPct(combinedProb)}</div></div>
      <div class="kpi-box"><div class="k-label">Valor Esperado (+EV Boleto)</div><div class="k-val" style="color:${combinedEV >= 0 ? "#10b981" : "#f59e0b"}">${fmtSignPct(combinedEV)}</div></div>
      <div class="kpi-box"><div class="k-label">Importe Apostado</div><div class="k-val">${fmtCOP(stake)}</div></div>
      <div class="kpi-box"><div class="k-label">Ganancia Posible Total</div><div class="k-val" style="color:#10b981">${fmtCOP(potentialReturn)}</div></div>
      <div class="kpi-box"><div class="k-label">Utilidad Libre</div><div class="k-val">+${fmtCOP(netProfit)}</div></div>
    </div>

    <div class="opta-report">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="font-family:'Outfit',sans-serif;font-size:17px">🎟️ Tu Boleto Wplay Paso a Paso (${chosen.length} ${chosen.length === 1 ? "Selección" : "Selecciones"})</h3>
        <button class="btn btn-ghost" id="btn-open-all-wplay" style="font-size:12.5px">🚀 Abrir todas las patas en Wplay</button>
      </div>
      ${legsHTML}
    </div>
  `;

  const btnAll = document.getElementById("btn-open-all-wplay");
  if (btnAll) {
    btnAll.addEventListener("click", () => {
      chosen.forEach((item) => {
        if (item.match.wplay_url) window.open(item.match.wplay_url, "_blank");
      });
    });
  }
}

// ---------------------------------------------------------------------------
// SECCIÓN APARTE 1: Especiales de Fútbol (Córners, SOT, Faltas, Tarjetas y Combinadas)
// ---------------------------------------------------------------------------
function renderSpecialsFootball() {
  const out = document.getElementById("sfb-output");
  if (!out || !STATE.today) return;

  const dateFilter = document.getElementById("sfb-date")?.value || "ALL";
  const type = document.getElementById("sfb-type").value;
  const league = document.getElementById("sfb-league").value;
  const sortDir = document.getElementById("sfb-sort").value;
  const q = document.getElementById("sfb-search").value.trim().toLowerCase();

  let fbMatches = (STATE.today.matches || []).filter(
    (m) => m.div !== "NBA" && m.opta_props && matchPassesDateFilter(m, dateFilter)
  );
  if (league !== "ALL") fbMatches = fbMatches.filter((m) => m.div === league);
  if (q) fbMatches = fbMatches.filter((m) => `${m.home} ${m.away}`.toLowerCase().includes(q));

  if (!fbMatches.length) {
    out.innerHTML = `<div class="opta-block">No hay partidos de fútbol para este filtro.</div>`;
    return;
  }

  if (type === "COMBO") {
    // Generador de Combinadas Especiales de Fútbol (Crear Apuesta / Parlay de Props)
    const combos = fbMatches
      .map((m) => {
        const p = m.opta_props;
        const p1x2 = m.probs?.["1x2"] || {};
        const pOver25 = m.probs?.ou25?.O || 0.5;
        // Elegir las 2 props más fuertes del partido
        const legs = [];
        if (p.corners.p_over_85 >= 0.62) {
          legs.push({ label: "Más de 8.5 Córners", prob: p.corners.p_over_85 });
        } else {
          legs.push({ label: "Menos de 10.5 Córners", prob: 1 - p.corners.p_over_105 });
        }
        if (p.sot.p_over_75 >= 0.60) {
          legs.push({ label: "Más de 7.5 Tiros al Arco (SOT)", prob: p.sot.p_over_75 });
        } else {
          legs.push({ label: "Más de 3.5 Tarjetas / Faltas Altas", prob: Math.max(p.cards.p_over_35, p.fouls.p_over_215) });
        }
        const favSide = p1x2.H >= p1x2.A ? `${m.home} o Empate (1X)` : `${m.away} o Empate (X2)`;
        const favProb = p1x2.H >= p1x2.A ? p1x2.H + p1x2.D : p1x2.A + p1x2.D;
        legs.push({ label: favSide, prob: favProb });

        const jointProb = legs[0].prob * legs[1].prob * legs[2].prob;
        const fairOdd = 1 / Math.max(jointProb, 0.05);
        return { m, legs, jointProb, fairOdd };
      })
      .sort((a, b) => b.jointProb - a.jointProb);

    const topMulti = combos.slice(0, 3);
    const multiProb = topMulti.reduce((acc, x) => acc * x.legs[0].prob, 1.0);
    const multiFairOdd = 1 / Math.max(multiProb, 0.05);

    out.innerHTML = `
      <div class="opta-report" style="margin-bottom:18px">
        <h4>🔥 PARLAY ESPECIAL DEL DÍA (3 PARTIDOS DISTINTOS — ALTA PROBABILIDAD OPTA)</h4>
        <p style="font-size:13px;color:#cbd5e1;margin-bottom:8px">
          Combinación de la métrica más sólida de los 3 partidos top de la cartelera:
          Probabilidad Combinada: <strong class="mono" style="color:#10b981">${fmtPct(multiProb)}</strong> ·
          Cuota Justa Mínima a exigir: <strong class="mono">@ ${fmtOdds(multiFairOdd)}</strong>
        </p>
        <div class="kpi-grid">
          ${topMulti
            .map(
              (c, i) => `
              <div class="kpi-box">
                <div class="k-label">Pata #${i + 1} · ${c.m.league?.flag || ""} ${c.m.home} vs ${c.m.away}</div>
                <div class="k-val" style="font-size:15px;color:#10b981">${c.legs[0].label}</div>
                <div style="font-size:12px;color:#94a3b8;margin-top:4px">Probabilidad Opta: <strong>${fmtPct(c.legs[0].prob)}</strong> (Cuota justa: ${fmtOdds(1 / c.legs[0].prob)})</div>
              </div>`
            )
            .join("")}
        </div>
      </div>

      <div class="opta-block">
        <h4>🧩 CREAR APUESTA (BET BUILDER MISMO PARTIDO: DOBLE OPORTUNIDAD + CÓRNERS + TIROS AL ARCO)</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Partido</th>
                <th>Selección 1 (Resultado)</th>
                <th>Selección 2 (Córners)</th>
                <th>Selección 3 (SOT / Tarjetas)</th>
                <th>Prob. Conjunta</th>
                <th>Cuota Justa</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody>
              ${combos
                .map(
                  (c) => `
                <tr>
                  <td>${fmtDateCO(c.m.kickoff)}</td>
                  <td><strong>${c.m.home} vs ${c.m.away}</strong></td>
                  <td>${c.legs[2].label} <span class="mono" style="color:#10b981">(${fmtPct(c.legs[2].prob, 0)})</span></td>
                  <td>${c.legs[0].label} <span class="mono" style="color:#10b981">(${fmtPct(c.legs[0].prob, 0)})</span></td>
                  <td>${c.legs[1].label} <span class="mono" style="color:#10b981">(${fmtPct(c.legs[1].prob, 0)})</span></td>
                  <td class="mono"><strong style="color:#10b981">${fmtPct(c.jointProb)}</strong></td>
                  <td class="mono"><strong>@ ${fmtOdds(c.fairOdd)}</strong></td>
                  <td>${c.m.wplay_url ? `<a href="${c.m.wplay_url}" target="_blank" class="btn btn-ghost" style="padding:4px 8px;font-size:11px;text-decoration:none">Crear en Wplay ↗</a>` : "—"}</td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
    return;
  }

  // Configuración según el tipo de métrica seleccionada (CORNERS, SOT, FOULS, CARDS)
  const cfgMap = {
    CORNERS: {
      title: "🚩 Ranking de Tiros de Esquina (Córners Esperados Poisson)",
      key: "corners",
      unit: "córners",
      l1: ["Más de 8.5 Córners", "p_over_85"],
      l2: ["Más de 9.5 Córners", "p_over_95"],
      l3: ["Más de 10.5 Córners", "p_over_105"],
    },
    SOT: {
      title: "🎯 Ranking de Tiros al Arco (Shots on Target - SOT)",
      key: "sot",
      unit: "tiros al arco",
      l1: ["Más de 7.5 SOT", "p_over_75"],
      l2: ["Más de 8.5 SOT", "p_over_85"],
      l3: ["Más de 9.5 SOT", "p_over_95"],
    },
    FOULS: {
      title: "🛑 Sección de Faltas Cometidas e Intensidad Defensiva",
      key: "fouls",
      unit: "faltas",
      l1: ["Más de 21.5 Faltas", "p_over_215"],
      l2: ["Más de 23.5 Faltas", "p_over_235"],
      l3: ["Más de 25.5 Faltas", "p_over_255"],
    },
    CARDS: {
      title: "🟨 Ranking de Tarjetas Disciplinarias (Amarillas Esperadas)",
      key: "cards",
      unit: "tarjetas",
      l1: ["Más de 3.5 Tarjetas", "p_over_35"],
      l2: ["Más de 4.5 Tarjetas", "p_over_45"],
      l3: ["Menos de 3.5 Tarjetas", "p_under_35"],
    },
  };

  const cfg = cfgMap[type];
  fbMatches.sort((a, b) => {
    const va = a.opta_props[cfg.key].total;
    const vb = b.opta_props[cfg.key].total;
    return sortDir === "HIGH" ? vb - va : va - vb;
  });

  const rowsHTML = fbMatches
    .map((m) => {
      const d = m.opta_props[cfg.key];
      const p1 = d[cfg.l1[1]];
      const p2 = d[cfg.l2[1]];
      const p3 = cfg.l3[1] === "p_under_35" ? 1 - d.p_over_35 : d[cfg.l3[1]];
      const bestLine =
        p1 >= 0.64
          ? `${cfg.l1[0]} (${fmtPct(p1)})`
          : p2 >= 0.56
          ? `${cfg.l2[0]} (${fmtPct(p2)})`
          : `Menos de línea alta (${fmtPct(1 - p2)})`;
      return `
        <tr>
          <td>${fmtDateCO(m.kickoff)}</td>
          <td>${m.league?.flag || ""} ${m.league?.name || m.div}</td>
          <td><strong>${m.home} vs ${m.away}</strong></td>
          <td class="mono">${d.home}</td>
          <td class="mono">${d.away}</td>
          <td class="mono"><strong style="color:#10b981;font-size:14px">${d.total} ${cfg.unit}</strong></td>
          <td class="mono"><strong>${fmtPct(p1)}</strong> <span style="color:#94a3b8">(@${fmtOdds(1 / Math.max(p1, 0.01))})</span></td>
          <td class="mono"><strong>${fmtPct(p2)}</strong> <span style="color:#94a3b8">(@${fmtOdds(1 / Math.max(p2, 0.01))})</span></td>
          <td class="mono"><strong>${fmtPct(p3)}</strong> <span style="color:#94a3b8">(@${fmtOdds(1 / Math.max(p3, 0.01))})</span></td>
          <td><span class="badge badge-value">${bestLine}</span></td>
        </tr>
      `;
    })
    .join("");

  out.innerHTML = `
    <div class="opta-block">
      <h4>${cfg.title}</h4>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Liga</th>
              <th>Encuentro</th>
              <th>Proy. Local</th>
              <th>Proy. Visit.</th>
              <th>Total Proyectado</th>
              <th>${cfg.l1[0]}</th>
              <th>${cfg.l2[0]}</th>
              <th>${cfg.l3[0]}</th>
              <th>Recomendación Opta</th>
            </tr>
          </thead>
          <tbody>${rowsHTML}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// SECCIÓN APARTE 2: Props por Jugador, Puntos Partido y Combinadas NBA
// ---------------------------------------------------------------------------
function populateNBAMatchSelect() {
  const sel = document.getElementById("snba-match");
  if (!sel || !STATE.today) return;
  const nbaMatches = (STATE.today.matches || []).filter((m) => m.div === "NBA");
  const cur = sel.value;
  sel.innerHTML =
    `<option value="ALL">Todos los partidos NBA (${nbaMatches.length} juegos)</option>` +
    nbaMatches.map((m) => `<option value="${m.id}">${m.home} vs ${m.away}</option>`).join("");
  if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
}

function renderSpecialsNBA() {
  const out = document.getElementById("snba-output");
  if (!out || !STATE.today) return;

  const dateFilter = document.getElementById("snba-date")?.value || "ALL";
  const type = document.getElementById("snba-type").value;
  const matchFilter = document.getElementById("snba-match").value;
  const sideFilter = document.getElementById("snba-side").value;
  const q = document.getElementById("snba-search").value.trim().toLowerCase();

  let nbaMatches = (STATE.today.matches || []).filter(
    (m) => m.div === "NBA" && matchPassesDateFilter(m, dateFilter)
  );
  if (matchFilter !== "ALL") nbaMatches = nbaMatches.filter((m) => m.id === matchFilter);

  if (!nbaMatches.length) {
    out.innerHTML = `<div class="opta-block">No hay partidos NBA cargados.</div>`;
    return;
  }

  if (type === "GAME_PTS") {
    const rows = nbaMatches
      .filter((m) => !q || `${m.home} ${m.away}`.toLowerCase().includes(q))
      .map((m) => {
        const bd = m.nba_breakdown || {};
        const totSel = (m.selections || []).find((s) => s.market === "total" && s.selection === "O");
        const totUnder = (m.selections || []).find((s) => s.market === "total" && s.selection === "U");
        const bestTot = (totSel?.p_real || 0) >= (totUnder?.p_real || 0) ? totSel : totUnder;
        return `
          <tr>
            <td>${fmtDateCO(m.kickoff)}</td>
            <td><strong>${m.home} vs ${m.away}</strong></td>
            <td class="mono">${bd.pace ?? "—"} pos</td>
            <td class="mono"><strong>${bd.home?.pts ?? m.lambda_home} pts</strong> (Q1: ${bd.home?.q1 ?? "—"} | H1: ${bd.home?.h1 ?? "—"})</td>
            <td class="mono"><strong>${bd.away?.pts ?? m.lambda_away} pts</strong> (Q1: ${bd.away?.q1 ?? "—"} | H1: ${bd.away?.h1 ?? "—"})</td>
            <td class="mono" style="color:#10b981;font-weight:700">${(m.lambda_home + m.lambda_away).toFixed(1)} pts</td>
            <td>${bestTot ? `<span class="badge badge-value">${bestTot.name} @ ${fmtOdds(bestTot.odds)} (${fmtPct(bestTot.p_real)})</span>` : "—"}</td>
            <td>${m.wplay_url ? `<a href="${m.wplay_url}" target="_blank" class="btn btn-ghost" style="padding:4px 8px;font-size:11px;text-decoration:none">Wplay ↗</a>` : "—"}</td>
          </tr>
        `;
      })
      .join("");

    out.innerHTML = `
      <div class="opta-block">
        <h4>🏀 CANTIDAD DE PUNTOS EN EL PARTIDO, POR EQUIPO, 1ER CUARTO (Q1) Y 1RA MITAD (H1)</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Hora (CO)</th>
                <th>Partido NBA</th>
                <th>Pace</th>
                <th>Proyección Local (Partido / Q1 / H1)</th>
                <th>Proyección Visitante (Partido / Q1 / H1)</th>
                <th>Total Proyectado</th>
                <th>Mejor Línea Total Wplay</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
    return;
  }

  if (type === "COMBO_NBA") {
    // Recolectar el mejor prop de cada partido para armar combinadas especiales NBA
    const bestPerMatch = [];
    for (const m of nbaMatches) {
      const props = (m.player_props || []).slice().sort((a, b) => b.rec_prob - a.rec_prob);
      const topProp = props[0];
      const topTeamSel = (m.selections || []).slice().sort((a, b) => (b.p_real || 0) - (a.p_real || 0))[0];
      if (topProp && topTeamSel) {
        const jointP = topProp.rec_prob * topTeamSel.p_real;
        const combOdd = topProp.rec_odds * topTeamSel.odds;
        bestPerMatch.push({ m, topProp, topTeamSel, jointP, combOdd });
      }
    }
    bestPerMatch.sort((a, b) => b.jointP - a.jointP);
    const top3Props = bestPerMatch.slice(0, 3);
    const parlayOdd = top3Props.reduce((acc, x) => acc * x.topProp.rec_odds, 1.0);
    const parlayProb = top3Props.reduce((acc, x) => acc * x.topProp.rec_prob, 1.0);

    out.innerHTML = `
      <div class="opta-report" style="margin-bottom:18px">
        <h4>🔥 PARLAY ESPECIAL DE JUGADORES NBA (TOP 3 PLAYER PROPS MÁS SÓLIDOS DE HOY EN WPLAY)</h4>
        <p style="font-size:13px;color:#cbd5e1;margin-bottom:8px">
          Cuota Combinada en Wplay.co: <strong class="mono" style="color:#10b981">@ ${parlayOdd.toFixed(2)}</strong> ·
          Probabilidad Real Conjunta: <strong class="mono">${fmtPct(parlayProb)}</strong>
        </p>
        <div class="kpi-grid">
          ${top3Props
            .map(
              (x, i) => `
              <div class="kpi-box">
                <div class="k-label">Pata #${i + 1} · ${x.m.home} vs ${x.m.away}</div>
                <div class="k-val" style="font-size:15px;color:#10b981">${x.topProp.player}: ${x.topProp.recommended} ${x.topProp.category}</div>
                <div style="font-size:12px;color:#94a3b8;margin-top:4px">
                  Cuota Wplay: <strong>@ ${fmtOdds(x.topProp.rec_odds)}</strong> · Prob. Sin Vig: <strong>${fmtPct(x.topProp.rec_prob)}</strong> (Proy: ${x.topProp.proj})
                </div>
              </div>`
            )
            .join("")}
        </div>
      </div>

      <div class="opta-block">
        <h4>🧩 CREAR APUESTA NBA POR PARTIDO (GANADOR / TOTAL + JUGADOR ESTRELLA EN WPLAY)</h4>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Partido NBA</th>
                <th>Pata 1 (Equipo / Total)</th>
                <th>Pata 2 (Jugador Estrella)</th>
                <th>Cuota Combinada</th>
                <th>Prob. Conjunta</th>
                <th>Abrir en Wplay</th>
              </tr>
            </thead>
            <tbody>
              ${bestPerMatch
                .map(
                  (x) => `
                <tr>
                  <td><strong>${x.m.home} vs ${x.m.away}</strong></td>
                  <td>${x.topTeamSel.market_name}: <strong>${x.topTeamSel.name}</strong> (@${fmtOdds(x.topTeamSel.odds)} · ${fmtPct(x.topTeamSel.p_real)})</td>
                  <td><strong>${x.topProp.player}</strong> (${x.topProp.category}): <strong>${x.topProp.recommended}</strong> (@${fmtOdds(x.topProp.rec_odds)} · ${fmtPct(x.topProp.rec_prob)})</td>
                  <td class="mono"><strong style="color:#10b981">@ ${x.combOdd.toFixed(2)}</strong></td>
                  <td class="mono"><strong>${fmtPct(x.jointP)}</strong></td>
                  <td>${x.m.wplay_url ? `<a href="${x.m.wplay_url}" target="_blank" class="btn btn-primary" style="padding:5px 10px;font-size:11.5px;text-decoration:none">🔗 Crear en Wplay ↗</a>` : "—"}</td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
    return;
  }

  // Filtrado por categoría de jugador: PTS_PLAYER, REB_PLAYER, AST_PLAYER
  const catName = type === "PTS_PLAYER" ? "Puntos" : type === "REB_PLAYER" ? "Rebotes" : "Asistencias";
  const allProps = [];
  for (const m of nbaMatches) {
    for (const pp of m.player_props || []) {
      if (pp.category !== catName) continue;
      if (sideFilter === "OVER" && !pp.recommended.startsWith("Más")) continue;
      if (sideFilter === "UNDER" && !pp.recommended.startsWith("Menos")) continue;
      if (q && !`${pp.player} ${pp.team} ${m.home} ${m.away}`.toLowerCase().includes(q)) continue;
      allProps.push({ m, pp });
    }
  }
  allProps.sort((a, b) => b.pp.rec_prob - a.pp.rec_prob);

  const rows = allProps
    .map(
      ({ m, pp }) => `
      <tr>
        <td><strong>${m.home} vs ${m.away}</strong></td>
        <td><strong>${pp.player}</strong></td>
        <td class="mono"><strong>${pp.line}</strong></td>
        <td class="mono" style="color:#67e8f9"><strong>${pp.proj}</strong></td>
        <td class="mono">${fmtOdds(pp.over_odds)} <span style="color:#94a3b8">(${fmtPct(pp.p_over)})</span></td>
        <td class="mono">${fmtOdds(pp.under_odds)} <span style="color:#94a3b8">(${fmtPct(pp.p_under)})</span></td>
        <td><span class="badge badge-value">${pp.recommended} @ ${fmtOdds(pp.rec_odds)} (${fmtPct(pp.rec_prob)})</span></td>
        <td>${m.wplay_url ? `<a href="${m.wplay_url}" target="_blank" class="btn btn-ghost" style="padding:4px 8px;font-size:11px;text-decoration:none">Apostar en Wplay ↗</a>` : "—"}</td>
      </tr>`
    )
    .join("");

  out.innerHTML = `
    <div class="opta-block">
      <h4>⛹️‍♂️ RANKING DE ${catName.toUpperCase()} POR JUGADOR EN WPLAY.CO (ORDENADO POR MAYOR PROBABILIDAD REAL)</h4>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Partido NBA</th>
              <th>Jugador</th>
              <th>Línea Wplay</th>
              <th>Proyección Opta</th>
              <th>Cuota Más de (Over)</th>
              <th>Cuota Menos de (Under)</th>
              <th>Selección Más Probable</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody>${rows || `<tr><td colspan="8">No hay jugadores para este filtro.</td></tr>`}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Pestaña 2: Analizador Manual
// ---------------------------------------------------------------------------
async function loadLabTeams(div) {
  const res = await fetch(`/api/leagues/${div}/teams`);
  const data = await res.json();
  const homeSel = document.getElementById("lab-home");
  const awaySel = document.getElementById("lab-away");
  homeSel.innerHTML = data.teams.map((t) => `<option value="${t}">${t}</option>`).join("");
  awaySel.innerHTML = data.teams.map((t, i) => `<option value="${t}" ${i === 1 ? "selected" : ""}>${t}</option>`).join("");
}

async function runLabMatchup(e) {
  if (e) e.preventDefault();
  const div = document.getElementById("lab-div").value;
  const home = document.getElementById("lab-home").value;
  const away = document.getElementById("lab-away").value;

  const num = (id) => {
    const v = parseFloat(document.getElementById(id).value);
    return isNaN(v) ? null : v;
  };

  const odds = {
    "1x2": { H: num("lab-1x2-h"), D: num("lab-1x2-d"), A: num("lab-1x2-a") },
    ou25: { O: num("lab-ou-o"), U: num("lab-ou-u") },
    btts: { Y: num("lab-btts-y"), N: num("lab-btts-n") },
    ah: { line: num("lab-ah-line"), H: num("lab-ah-h"), A: num("lab-ah-a") },
  };

  const out = document.getElementById("lab-result");
  out.innerHTML = `<div class="card">Calculando matriz Poisson Dixon-Coles y EV...</div>`;

  const res = await fetch("/api/matchup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ div, home, away, odds }),
  });
  const m = await res.json();
  if (!res.ok) {
    out.innerHTML = `<div class="card" style="color:#f43f5e">${m.detail || "Error al analizar"}</div>`;
    return;
  }
  out.innerHTML = renderOptaExecutiveReport(m, true);
  out.querySelectorAll(".btn-save-pick").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sel = m.selections.find((s) => s.key === btn.dataset.key);
      if (!sel) return;
      await saveManualPick(m, sel);
      btn.textContent = "✓ Guardado";
      btn.disabled = true;
    });
  });
}

// ---------------------------------------------------------------------------
// Pestaña 3: Ratings por liga
// ---------------------------------------------------------------------------
async function loadRatingsTable(div) {
  const tbody = document.querySelector("#ratings-table tbody");
  const meta = document.getElementById("ratings-meta");
  tbody.innerHTML = `<tr><td colspan="11">Cargando ratings xG...</td></tr>`;
  const res = await fetch(`/api/leagues/${div}/teams`);
  const data = await res.json();
  meta.innerHTML = `<p style="font-size:13px;color:#94a3b8;margin-bottom:12px">
    Media de goles esperados local: <strong class="mono">${data.mu_home}</strong> · Visitante: <strong class="mono">${data.mu_away}</strong> · Señal xG Opta/Understat activa: <strong>${data.uses_xg ? "Sí" : "Proxy tiros"}</strong>
  </p>`;
  tbody.innerHTML = (data.ratings || [])
    .map((r, idx) => {
      const formHTML = (r.form || [])
        .map((f) => `<span class="form-pill form-${f}">${f}</span>`)
        .join("");
      return `
        <tr>
          <td class="mono">${idx + 1}</td>
          <td><strong>${r.team}</strong></td>
          <td class="mono">${r.played}</td>
          <td class="mono" style="color:#10b981;font-weight:700">${r.power.toFixed(2)}</td>
          <td class="mono">${r.att.toFixed(2)}</td>
          <td class="mono">${r.defn.toFixed(2)}</td>
          <td class="mono">${r.xg_for ?? "—"}</td>
          <td class="mono">${r.xg_against ?? "—"}</td>
          <td class="mono" style="color:${(r.xg_diff || 0) >= 0 ? "#10b981" : "#f43f5e"}">${r.xg_diff !== null && r.xg_diff !== undefined ? (r.xg_diff >= 0 ? "+" : "") + r.xg_diff : "—"}</td>
          <td class="mono">${r.goals_for} / ${r.goals_against}</td>
          <td>${formHTML}</td>
        </tr>
      `;
    })
    .join("");
}

// ---------------------------------------------------------------------------
// Pestaña 4: Historial & CLV
// ---------------------------------------------------------------------------
async function loadHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  const s = data.summary || {};

  document.getElementById("history-kpis").innerHTML = `
    <div class="kpi-box"><div class="k-label">Total Picks</div><div class="k-val">${s.total || 0} (${s.open || 0} abiertos)</div></div>
    <div class="kpi-box"><div class="k-label">Tasa de Acierto</div><div class="k-val">${fmtPct(s.hit_rate)}</div></div>
    <div class="kpi-box"><div class="k-label">EV Medio</div><div class="k-val" style="color:#10b981">${fmtSignPct(s.avg_ev)}</div></div>
    <div class="kpi-box"><div class="k-label">CLV Medio (Closing Line)</div><div class="k-val">${fmtSignPct(s.avg_clv)}</div></div>
    <div class="kpi-box"><div class="k-label">ROI Real</div><div class="k-val">${fmtSignPct(s.roi)}</div></div>
    <div class="kpi-box"><div class="k-label">Beneficio Neto</div><div class="k-val">${fmtCOP(s.profit || 0)}</div></div>
  `;

  const tbody = document.querySelector("#history-table tbody");
  if (!data.picks?.length) {
    tbody.innerHTML = `<tr><td colspan="12">Aún no hay picks registrados. Puedes registrar cualquier pick desde el Radar o el Analizador Manual.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.picks
    .map(
      (p) => `
      <tr>
        <td>${fmtDateCO(p.kickoff)}</td>
        <td>${p.div}</td>
        <td><strong>${p.home} vs ${p.away}</strong></td>
        <td>${p.name}</td>
        <td class="mono">${fmtOdds(p.odds)}</td>
        <td class="mono">${fmtPct(p.p_real)}</td>
        <td class="mono" style="color:#10b981">${fmtSignPct(p.ev)}</td>
        <td class="mono">${fmtCOP(p.stake_amount)}</td>
        <td><span class="badge badge-nobet">${p.status.toUpperCase()}${p.score ? " (" + p.score + ")" : ""}</span></td>
        <td class="mono">${fmtSignPct(p.clv)}</td>
        <td class="mono" style="color:${(p.profit || 0) >= 0 ? "#10b981" : "#f43f5e"}">${p.profit !== null ? fmtCOP(p.profit) : "—"}</td>
        <td><button class="btn btn-ghost btn-del-pick" style="padding:3px 7px;font-size:11px" data-id="${p.id}">✕</button></td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll(".btn-del-pick").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/picks/${btn.dataset.id}`, { method: "DELETE" });
      loadHistory();
    });
  });
}

// ---------------------------------------------------------------------------
// Pestaña 5: Backtest & Calibración
// ---------------------------------------------------------------------------
async function loadBacktest() {
  const basis = document.getElementById("bt-basis").value;
  const kpis = document.getElementById("bt-kpis");
  kpis.innerHTML = `<div class="kpi-box"><div class="k-label">Ejecutando walk-forward backtest...</div></div>`;
  const res = await fetch(`/api/backtest?basis=${basis}`);
  const d = await res.json();
  const cal = d.calibration || {};

  kpis.innerHTML = `
    <div class="kpi-box"><div class="k-label">Partidos Calibrados</div><div class="k-val">${cal.n_matches || 0}</div></div>
    <div class="kpi-box"><div class="k-label">Brier Score (Consenso)</div><div class="k-val">${cal.brier_blend ? cal.brier_blend.toFixed(3) : "—"}</div></div>
    <div class="kpi-box"><div class="k-label">Apuestas +EV Simuladas</div><div class="k-val">${d.n_bets || 0}</div></div>
    <div class="kpi-box"><div class="k-label">EV Medio Detectado</div><div class="k-val" style="color:#10b981">${fmtSignPct(d.avg_ev)}</div></div>
    <div class="kpi-box"><div class="k-label">% Apuestas que baten Cierre (CLV+)</div><div class="k-val">${fmtPct(d.positive_clv_rate)}</div></div>
    <div class="kpi-box"><div class="k-label">ROI Unidad Plana</div><div class="k-val">${fmtSignPct(d.flat_roi)}</div></div>
  `;

  document.getElementById("bt-calibration").innerHTML = `
    <table class="data-table">
      <thead><tr><th>Tramo Probabilidad</th><th>P_Modelo Media</th><th>Frecuencia Real</th><th>Muestra</th></tr></thead>
      <tbody>
        ${(cal.bins || [])
          .map(
            (b) => `<tr>
              <td class="mono">${Math.floor(b.p * 10) * 10}% – ${Math.floor(b.p * 10) * 10 + 10}%</td>
              <td class="mono">${fmtPct(b.p)}</td>
              <td class="mono"><strong>${fmtPct(b.freq)}</strong></td>
              <td class="mono">${b.n}</td>
            </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;

  document.querySelector("#bt-bets-table tbody").innerHTML = (d.bets || [])
    .slice()
    .reverse()
    .slice(0, 60)
    .map(
      (b) => `<tr>
        <td>${b.date}</td>
        <td><strong>${b.match}</strong> (${b.score})</td>
        <td>${b.pick}</td>
        <td class="mono">${fmtOdds(b.odds)}</td>
        <td class="mono" style="color:#10b981">${fmtSignPct(b.ev)}</td>
        <td>${b.status.toUpperCase()}</td>
        <td class="mono" style="color:${b.units >= 0 ? "#10b981" : "#f43f5e"}">${b.units >= 0 ? "+" : ""}${b.units.toFixed(2)}u</td>
      </tr>`
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Inicialización y Eventos
// ---------------------------------------------------------------------------
function updateSidebarSettings(s) {
  document.getElementById("sb-bankroll").textContent = fmtCOP(s.bankroll);
  const maxCop = s.bankroll * s.max_stake_pct;
  document.getElementById("sb-kelly").textContent = `Kelly ${(s.kelly_fraction * 100).toFixed(0)}% · Tope ${(s.max_stake_pct * 100).toFixed(1)}% (${fmtCOP(maxCop)})`;
  document.getElementById("top-minev").textContent = `≥ ${(s.min_ev * 100).toFixed(1)}%`;

  document.getElementById("set-bankroll").value = s.bankroll;
  document.getElementById("set-minbet").value = s.min_bet || 1000;
  document.getElementById("set-basis").value = s.price_basis || "best";
  document.getElementById("set-kelly").value = s.kelly_fraction;
  document.getElementById("set-maxstake").value = (s.max_stake_pct * 100).toFixed(1);
  document.getElementById("set-minev").value = (s.min_ev * 100).toFixed(1);
  document.getElementById("set-weight").value = s.model_weight;
}

async function initApp() {
  const metaRes = await fetch("/api/meta");
  STATE.meta = await metaRes.json();
  updateSidebarSettings(STATE.meta.settings);

  if (STATE.meta.odds_api_enabled) {
    document.getElementById("sb-source").textContent = `The Odds API + football-data (Restantes: ${STATE.meta.odds_api_quota?.remaining ?? "—"})`;
  }

  // Cargar radar inicial
  const todayRes = await fetch("/api/picks/today");
  STATE.today = await todayRes.json();
  populateDateSelects();
  renderTodayMatches();

  // Cargar equipos en analizador manual
  await loadLabTeams(document.getElementById("lab-div").value);
}

document.addEventListener("DOMContentLoaded", async () => {
  // Autenticación y Bloqueo
  const loginForm = document.getElementById("login-form");
  const btnTogglePwd = document.getElementById("btn-toggle-pwd");
  const btnLock = document.getElementById("btn-lock");
  const formChangePwd = document.getElementById("form-change-pwd");

  if (btnTogglePwd) {
    btnTogglePwd.addEventListener("click", () => {
      const inp = document.getElementById("login-password");
      if (inp) inp.type = inp.type === "password" ? "text" : "password";
    });
  }

  if (btnLock) {
    btnLock.addEventListener("click", () => {
      localStorage.removeItem("quantbet_token");
      AUTH_TOKEN = "";
      showLoginOverlay();
    });
  }

  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pwd = document.getElementById("login-password")?.value || "";
      const errBox = document.getElementById("login-error");
      const btn = document.getElementById("btn-submit-login");
      if (btn) {
        btn.textContent = "Verificando...";
        btn.disabled = true;
      }
      try {
        const res = await _originalFetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: pwd }),
        });
        const data = await res.json();
        if (res.ok && data.success) {
          AUTH_TOKEN = data.token;
          localStorage.setItem("quantbet_token", AUTH_TOKEN);
          document.getElementById("login-password").value = "";
          hideLoginOverlay();
          await initApp();
        } else {
          if (errBox) {
            errBox.textContent = data.detail || "Contraseña incorrecta.";
            errBox.style.display = "block";
          }
        }
      } catch (err) {
        if (errBox) {
          errBox.textContent = "Error de conexión con el servidor.";
          errBox.style.display = "block";
        }
      } finally {
        if (btn) {
          btn.textContent = "Desbloquear Panel Seguro 🔓";
          btn.disabled = false;
        }
      }
    });
  }

  if (formChangePwd) {
    formChangePwd.addEventListener("submit", async (e) => {
      e.preventDefault();
      const cur = document.getElementById("pwd-current")?.value || "";
      const nw = document.getElementById("pwd-new")?.value || "";
      const msg = document.getElementById("pwd-saved-msg");
      try {
        const res = await fetch("/api/auth/change-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password: cur, new_password: nw }),
        });
        const data = await res.json();
        if (res.ok && data.success) {
          AUTH_TOKEN = data.token;
          localStorage.setItem("quantbet_token", AUTH_TOKEN);
          if (msg) {
            msg.textContent = "✓ Contraseña actualizada";
            msg.style.color = "#10b981";
          }
          formChangePwd.reset();
        } else {
          if (msg) {
            msg.textContent = "✗ " + (data.detail || "Error al cambiar clave");
            msg.style.color = "#f43f5e";
          }
        }
      } catch (err) {
        if (msg) msg.textContent = "✗ Error de red";
      }
    });
  }

  // Verificar sesión antes de cargar datos
  let isAuth = false;
  if (AUTH_TOKEN) {
    try {
      const stRes = await _originalFetch("/api/auth/status", {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
      });
      const stData = await stRes.json();
      isAuth = Boolean(stData.authenticated);
    } catch {
      isAuth = false;
    }
  }

  if (!isAuth) {
    showLoginOverlay();
  } else {
    hideLoginOverlay();
    initApp();
  }

  // Navegación por pestañas
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      document.getElementById(`tab-${tab}`).classList.add("active");

      if (tab === "live") {
        loadLiveEvents();
        loadNbaLiveTracker();
      }
      if (tab === "builder") renderWplayBuilder();
      if (tab === "specials-fb") renderSpecialsFootball();
      if (tab === "specials-nba") {
        loadNbaLiveTracker();
        populateNBAMatchSelect();
        renderSpecialsNBA();
      }
      if (tab === "ratings") loadRatingsTable(document.getElementById("ratings-div").value);
      if (tab === "history") loadHistory();
      if (tab === "backtest") loadBacktest();
      if (tab === "senior") loadSeniorReport();
    });
  });

  const btnRunSenior = document.getElementById("btn-run-senior");
  if (btnRunSenior) {
    btnRunSenior.addEventListener("click", loadSeniorReport);
  }

  const btnRefreshLive = document.getElementById("btn-refresh-live");
  if (btnRefreshLive) {
    btnRefreshLive.addEventListener("click", () => {
      loadLiveEvents();
      loadNbaLiveTracker();
    });
  }

  // Eventos del Armador Wplay
  ["bld-date", "bld-market", "bld-mode", "bld-legs", "bld-stake"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", renderWplayBuilder);
  });

  // Eventos de Especiales Fútbol
  ["sfb-date", "sfb-type", "sfb-league", "sfb-sort", "sfb-search"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", renderSpecialsFootball);
  });

  // Eventos de Props & Especiales NBA
  ["snba-date", "snba-type", "snba-match", "snba-side", "snba-search"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", renderSpecialsNBA);
  });

  const btnGoto = document.getElementById("btn-goto-builder");
  if (btnGoto) {
    btnGoto.addEventListener("click", () => {
      const bldNav = document.querySelector('.nav-item[data-tab="builder"]');
      if (bldNav) bldNav.click();
    });
  }

  // Filtros del radar
  ["filter-date", "filter-league", "filter-signal", "filter-market", "filter-search"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", renderTodayMatches);
  });

  // Cambio de liga en Analizador Manual
  document.getElementById("lab-div").addEventListener("change", (e) => loadLabTeams(e.target.value));
  document.getElementById("form-matchup").addEventListener("submit", runLabMatchup);

  document.getElementById("btn-lab-demo").addEventListener("click", () => {
    document.getElementById("lab-1x2-h").value = "1.95";
    document.getElementById("lab-1x2-d").value = "3.60";
    document.getElementById("lab-1x2-a").value = "4.10";
    document.getElementById("lab-ou-o").value = "1.88";
    document.getElementById("lab-ou-u").value = "1.96";
    document.getElementById("lab-btts-y").value = "1.80";
    document.getElementById("lab-btts-n").value = "2.00";
    document.getElementById("lab-ah-line").value = "-0.5";
    document.getElementById("lab-ah-h").value = "1.95";
    document.getElementById("lab-ah-a").value = "1.92";
    runLabMatchup();
  });

  // Cambio de liga en Ratings
  document.getElementById("ratings-div").addEventListener("change", (e) => loadRatingsTable(e.target.value));

  // Cambio de base en Backtest
  document.getElementById("bt-basis").addEventListener("change", loadBacktest);

  // Guardar ajustes
  document.getElementById("form-settings").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      bankroll: parseFloat(document.getElementById("set-bankroll").value),
      min_bet: parseFloat(document.getElementById("set-minbet").value),
      price_basis: document.getElementById("set-basis").value,
      kelly_fraction: parseFloat(document.getElementById("set-kelly").value),
      max_stake_pct: parseFloat(document.getElementById("set-maxstake").value) / 100,
      min_ev: parseFloat(document.getElementById("set-minev").value) / 100,
      model_weight: parseFloat(document.getElementById("set-weight").value),
    };
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const saved = await res.json();
    updateSidebarSettings(saved);
    document.getElementById("settings-saved-msg").textContent = "✓ Parámetros guardados y recálculo aplicado.";
    const todayRes = await fetch("/api/picks/today?force=true");
    STATE.today = await todayRes.json();
    renderTodayMatches();
  });

  // Botón actualizar ahora + Auto-actualización cada 30 segundos
  async function performQuickSync(isAuto = false) {
    const btn = document.getElementById("btn-sync");
    const activeTab = document.querySelector(".nav-item.active")?.dataset?.tab;
    if (!isAuto && btn) {
      btn.textContent = "⏳ Actualizando...";
      btn.disabled = true;
    }
    try {
      if (activeTab === "live") {
        await loadLiveEvents();
        await loadNbaLiveTracker();
      } else {
        if (!isAuto) {
          await fetch("/api/run", { method: "POST" });
        }
        const todayRes = await fetch(isAuto ? "/api/picks/today" : "/api/picks/today?force=true");
        STATE.today = await todayRes.json();
        populateDateSelects();
        renderTodayMatches();
        if (activeTab === "builder") renderWplayBuilder();
        if (activeTab === "specials-fb") renderSpecialsFootball();
        if (activeTab === "specials-nba") {
          await loadNbaLiveTracker();
          populateNBAMatchSelect();
          renderSpecialsNBA();
        }
      }
    } catch (err) {
      console.warn("Error en actualización:", err);
    } finally {
      if (!isAuto && btn) {
        btn.textContent = "🔄 Actualizar Datos Ahora";
        btn.disabled = false;
      }
    }
  }

  document.getElementById("btn-sync").addEventListener("click", () => performQuickSync(false));

  // Temporizador automático cada 30 segundos
  let syncCountdown = 30;
  setInterval(() => {
    const chk = document.getElementById("chk-auto-30s");
    const lbl = document.getElementById("auto-sync-timer");
    if (!chk || !chk.checked) {
      if (lbl) lbl.textContent = "Pausado";
      return;
    }
    syncCountdown -= 1;
    if (syncCountdown <= 0) {
      syncCountdown = 30;
      if (lbl) lbl.textContent = "🔄...";
      performQuickSync(true);
    } else if (lbl) {
      lbl.textContent = `${syncCountdown}s`;
    }
  }, 1000);

  // Cerrar modal
  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("match-modal").classList.add("hidden");
  });
  document.getElementById("match-modal").addEventListener("click", (e) => {
    if (e.target.id === "match-modal") e.target.classList.add("hidden");
  });
});
