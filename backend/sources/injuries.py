"""Fuente de lesiones y ausencias confirmadas en tiempo real (ESPN API).

Obtiene el parte médico oficial de la NBA para:
1. Excluir jugadores 'Out' de las recomendaciones de Player Props.
2. Ajustar la proyección ofensiva de los equipos según sus bajas confirmadas.
3. Mostrar alertas de ausencias en la interfaz web.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

log = logging.getLogger("quantbet.injuries")

NBA_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
_nba_inj_cache: dict[str, Any] = {"ts": 0.0, "data": {}}


def fetch_nba_injuries(force: bool = False) -> dict[str, list[dict]]:
    """Retorna diccionario { 'Team Display Name': [ {player, status, detail} ] }."""
    if not force and _nba_inj_cache["data"] and (time.time() - _nba_inj_cache["ts"]) < 1800:
        return _nba_inj_cache["data"]

    req = urllib.request.Request(
        NBA_INJURIES_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantBet/1.0"},
    )
    out_map: dict[str, list[dict]] = {}
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        for team_blk in raw.get("injuries", []):
            tname = team_blk.get("displayName", "").strip()
            if not tname:
                continue
            plist = []
            for item in team_blk.get("injuries", []):
                ath = item.get("athlete", {})
                pname = ath.get("displayName", "").strip()
                status = item.get("status", "Questionable").strip()
                comment = item.get("shortComment", "") or ""
                if pname:
                    plist.append({
                        "player": pname,
                        "status": status,
                        "comment": comment[:120],
                    })
            if plist:
                out_map[tname] = plist
        _nba_inj_cache["ts"] = time.time()
        _nba_inj_cache["data"] = out_map
    except Exception as exc:
        log.warning("No se pudo obtener parte de lesiones NBA (%s)", exc)
    return _nba_inj_cache["data"]


def get_team_injuries(team_name: str, inj_map: dict[str, list[dict]] | None = None) -> list[dict]:
    if inj_map is None:
        inj_map = fetch_nba_injuries()
    if team_name in inj_map:
        return inj_map[team_name]
    low = team_name.lower()
    for k, v in inj_map.items():
        if low in k.lower() or k.lower() in low:
            return v
    return []


def is_player_out(player_name: str, inj_list: list[dict]) -> bool:
    low = player_name.lower().strip()
    for item in inj_list:
        if low in item["player"].lower() or item["player"].lower() in low:
            if item["status"].lower() in ("out", "doubtful", "suspended"):
                return True
    return False
