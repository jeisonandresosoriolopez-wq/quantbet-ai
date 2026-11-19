"""Módulo de análisis de NBA en Vivo y Detección de Sobre-reacción de la Casa (+EV In-Play).

Compara en tiempo real el ritmo (Pace) y anotación de los partidos de la NBA
contra las proyecciones pre-partido para detectar:
1. Sobre-reacción de totales (líneas infladas por 1Q explosivo -> Señal UNDER).
2. Oportunidades de Hándicap con colchón (reversión tras rachas transitorias de un equipo).
3. Puntos por minuto requeridos vs promedio de liga.
"""
from __future__ import annotations

import json
import logging
import math
import urllib.request
from typing import Any

log = logging.getLogger("quantbet.nba_live")

NBA_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
DEFAULT_AVG_TOTAL = 227.5
LEAGUE_PTS_PER_MIN = 2.37  # Promedio NBA: ~114 puntos en 48 minutos por equipo -> 2.37 pts/min combinados


def _fetch_espn_nba_raw() -> list[dict]:
    req = urllib.request.Request(NBA_SCOREBOARD_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("events", [])
    except Exception as exc:
        log.warning("Error fetching ESPN NBA live scoreboard: %s", exc)
        return []


def analyze_live_nba() -> dict[str, Any]:
    events = _fetch_espn_nba_raw()
    live_matches = []
    finished_matches = []
    upcoming_matches = []

    for ev in events:
        status_blk = ev.get("status", {})
        type_blk = status_blk.get("type", {})
        state = type_blk.get("state")  # 'in', 'post', 'pre'
        detail = type_blk.get("detail", "")
        period = status_blk.get("period", 0)
        display_clock = status_blk.get("displayClock", "0:00")

        comp = ev.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue

        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_name = home_comp.get("team", {}).get("displayName", "Local")
        away_name = away_comp.get("team", {}).get("displayName", "Visitante")
        home_score = int(home_comp.get("score") or 0)
        away_score = int(away_comp.get("score") or 0)
        total_pts = home_score + away_score
        margin = home_score - away_score  # > 0 si gana local

        # Cuartos
        h_lines = [int(ls.get("value") or 0) for ls in home_comp.get("linescores", [])]
        a_lines = [int(ls.get("value") or 0) for ls in away_comp.get("linescores", [])]

        if state == "in":
            # Minutos transcurridos
            try:
                parts = display_clock.split(":")
                clk_min = float(parts[0])
                clk_sec = float(parts[1]) if len(parts) > 1 else 0.0
                rem_in_quarter = clk_min + (clk_sec / 60.0)
            except Exception:
                rem_in_quarter = 0.0

            if "half" in detail.lower() or "descanso" in detail.lower():
                played_mins = 24.0
                remaining_mins = 24.0
            elif period <= 4:
                played_mins = max(0.5, (period - 1) * 12.0 + (12.0 - rem_in_quarter))
                remaining_mins = max(0.5, 48.0 - played_mins)
            else:
                played_mins = 48.0 + (period - 4) * 5.0 - rem_in_quarter
                remaining_mins = max(0.5, rem_in_quarter)

            # Ritmo actual extrapolado a 48 minutos
            current_pace_48 = (total_pts / played_mins) * 48.0

            # Puntos esperados normales hasta este minuto
            expected_total_now = (DEFAULT_AVG_TOTAL / 48.0) * played_mins
            pace_diff = total_pts - expected_total_now

            # Estimación de línea viva de las casas (Wplay pondera ritmo reciente vs media histórica)
            expected_remaining = DEFAULT_AVG_TOTAL * (remaining_mins / 48.0)
            pace_remaining = (total_pts / played_mins) * remaining_mins
            live_line_calc = total_pts + (0.50 * pace_remaining + 0.50 * expected_remaining)
            live_line_half = math.floor(live_line_calc) + 0.5

            req_pts_per_min = round((live_line_half - total_pts) / remaining_mins, 2) if remaining_mins > 0 else 0.0

            # Estado de Ritmo
            if pace_diff >= 6.0:
                pace_status = "🔥 SOBRECALENTADO"
                pace_badge = "overheated"
                overreaction_level = "Alta"
            elif pace_diff <= -6.0:
                pace_status = "❄️ RITMO CONGELADO"
                pace_badge = "cold"
                overreaction_level = "Baja"
            else:
                pace_status = "⚖️ RITMO EQUILIBRADO"
                pace_badge = "normal"
                overreaction_level = "Normal"

            signals = []
            # 1. Señal de Totales (Over / Under)
            if pace_diff >= 5.0 and remaining_mins >= 10.0:
                p_under = round(min(0.75, 0.54 + (pace_diff / 45.0)), 3)
                ev_under = round((p_under * 1.80) - 1.0, 3)
                signals.append({
                    "tipo": "TOTALES_UNDER",
                    "titulo": f"Menos de {live_line_half} Puntos",
                    "cuota_aprox": 1.80,
                    "prob_real": p_under,
                    "ev": f"+{round(ev_under * 100, 1)}%",
                    "badge": "🚨 ALERTA VALOR UNDER",
                    "razon": f"Línea de la casa inflada (+{round(pace_diff, 1)} pts). Requieren {req_pts_per_min} pts/min en los {round(remaining_mins, 1)} min restantes (Media liga: 2.37 pts/min)."
                })
            elif pace_diff <= -5.0 and remaining_mins >= 10.0:
                p_over = round(min(0.73, 0.54 + (abs(pace_diff) / 45.0)), 3)
                ev_over = round((p_over * 1.82) - 1.0, 3)
                signals.append({
                    "tipo": "TOTALES_OVER",
                    "titulo": f"Más de {live_line_half} Puntos",
                    "cuota_aprox": 1.82,
                    "prob_real": p_over,
                    "ev": f"+{round(ev_over * 100, 1)}%",
                    "badge": "⚡ ALERTA VALOR OVER",
                    "razon": f"Ritmo castigado (-{round(abs(pace_diff), 1)} pts). Se proyecta repunte defensivo/ofensivo hacia la media."
                })

            # 2. Señal de Hándicap con Colchón
            abs_margin = abs(margin)
            if abs_margin >= 4 and remaining_mins >= 12.0:
                trailing_team = home_name if margin < 0 else away_name
                is_home = (trailing_team == home_name)
                spread_val = math.ceil(abs_margin + (2.5 if is_home else 1.5)) + 0.5
                p_cover = round(0.58 + (0.07 if is_home else 0.03), 3)
                ev_cover = round((p_cover * 1.85) - 1.0, 3)
                signals.append({
                    "tipo": "HANDICAP_COLCHON",
                    "titulo": f"{trailing_team} (+{spread_val})",
                    "cuota_aprox": 1.85,
                    "prob_real": p_cover,
                    "ev": f"+{round(ev_cover * 100, 1)}%",
                    "badge": "🛡️ HÁNDICAP CON COLCHÓN",
                    "razon": f"Racha transitoria de {abs_margin} pts. {'Localía respalda la reacción para apretar el marcador' if is_home else 'Margen inflado con alto valor de cobertura'}."
                })

            live_matches.append({
                "id": ev.get("id"),
                "home": home_name,
                "away": away_name,
                "score_home": home_score,
                "score_away": away_score,
                "total_pts": total_pts,
                "margin": margin,
                "period": period,
                "clock": display_clock,
                "status_detail": detail,
                "played_mins": round(played_mins, 1),
                "remaining_mins": round(remaining_mins, 1),
                "q_home": h_lines,
                "q_away": a_lines,
                "pace_status": pace_status,
                "pace_badge": pace_badge,
                "pace_diff": round(pace_diff, 1),
                "live_line_total": live_line_half,
                "req_pts_per_min": req_pts_per_min,
                "signals": signals,
            })
        elif state == "post":
            finished_matches.append({
                "id": ev.get("id"),
                "home": home_name,
                "away": away_name,
                "score_home": home_score,
                "score_away": away_score,
                "total_pts": total_pts,
                "detail": detail
            })
        else:
            upcoming_matches.append({
                "id": ev.get("id"),
                "home": home_name,
                "away": away_name,
                "detail": detail
            })

    return {
        "live_count": len(live_matches),
        "live_matches": live_matches,
        "finished_count": len(finished_matches),
        "finished_matches": finished_matches,
        "upcoming_count": len(upcoming_matches),
    }
