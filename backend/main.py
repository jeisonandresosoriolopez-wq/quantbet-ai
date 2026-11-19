"""API web con FastAPI + tarea automática en segundo plano + servidor de frontend."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, db, service
from .sources import odds_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("quantbet.main")


async def _background_worker():
    """Ejecuta el análisis inicial al arrancar y luego cada 6 horas."""
    await asyncio.sleep(5)
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, service.run_daily, False)
        except Exception as exc:  # noqa: BLE001
            log.warning("Error en ciclo automático: %s", exc)
        await asyncio.sleep(6 * 3600)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    task = asyncio.create_task(_background_worker())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Opta QuantBet AI", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Rutas públicas sin autenticación requerida
    if path.startswith("/api/") and path not in ("/api/auth/login", "/api/auth/status"):
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "x-auth-token" in request.headers:
            token = request.headers["x-auth-token"].strip()
        else:
            token = request.query_params.get("token", "").strip()

        if not auth.verify_token(token):
            return JSONResponse(status_code=401, content={"detail": "Acceso protegido. Requiere contraseña de acceso."})

    return await call_next(request)


# --------------------------------------------------------------------------- #
# Modelos de entrada
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MatchupRequest(BaseModel):
    div: str
    home: str
    away: str
    odds: dict[str, Any] | None = None


class PickCreateRequest(BaseModel):
    match_id: str | None = None
    div: str
    kickoff: str | None = None
    home: str
    away: str
    market: str
    selection: str
    line: float | None = None
    name: str
    odds: float
    p_model: float
    p_market: float | None = None
    p_real: float
    stake_pct: float | None = None
    stake_amount: float | None = None
    bookmaker: str | None = None


# --------------------------------------------------------------------------- #
# Endpoints de Autenticación & Seguridad
# --------------------------------------------------------------------------- #
@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest):
    if not auth.verify_password(req.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta. Por favor verifica e intenta de nuevo.")
    token = auth.generate_token(req.password)
    return {"success": True, "token": token}


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else request.headers.get("x-auth-token", "")
    return {"authenticated": auth.verify_token(token)}


@app.post("/api/auth/change-password")
def api_auth_change_password(req: ChangePasswordRequest):
    if not auth.verify_password(req.current_password):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    if len(req.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 4 caracteres.")
    token = auth.set_new_password(req.new_password)
    return {"success": True, "token": token, "message": "Contraseña actualizada exitosamente."}


# --------------------------------------------------------------------------- #
# Endpoints API
# --------------------------------------------------------------------------- #
@app.get("/api/meta")
def api_meta():
    return {
        "leagues": config.LEAGUES,
        "settings": db.get_settings(),
        "odds_api_enabled": odds_api.enabled(),
        "odds_api_quota": odds_api.quota(),
        "state": service.STATE,
        "local_tz": config.LOCAL_TZ,
    }


@app.get("/api/picks/today")
def api_picks_today(force: bool = False):
    data = service.analyze_upcoming(force=force)
    return data


@app.get("/api/live")
def api_live():
    """Partidos EN VIVO en este instante desde Wplay.co con cálculo de probabilidad sin vig."""
    from .sources import wplay
    from .model import value
    settings = db.get_settings()
    events = wplay.fetch_live_events()
    out = []
    for ev in events:
        o = ev["odds"]
        if o["D"] is not None:
            p_h, p_d, p_a = value.devig([o["H"], o["D"], o["A"]])
            probs = {"H": round(p_h, 3), "D": round(p_d, 3), "A": round(p_a, 3)}
            best_side = max([("H", ev["home"], p_h, o["H"]), ("D", "Empate", p_d, o["D"]), ("A", ev["away"], p_a, o["A"])], key=lambda x: x[2])
        else:
            p_h, p_a = value.devig([o["H"], o["A"]])
            probs = {"H": round(p_h, 3), "D": None, "A": round(p_a, 3)}
            best_side = max([("H", ev["home"], p_h, o["H"]), ("A", ev["away"], p_a, o["A"])], key=lambda x: x[2])

        # Cálculo de Kelly Fraccional para el lado más probable
        st = value.stake(0.03, best_side[3], 15, settings)
        ev["probs"] = probs
        ev["recommended"] = {
            "side": best_side[0],
            "name": best_side[1],
            "prob": best_side[2],
            "odds": best_side[3],
            "stake_amount": st["stake_amount"],
        }
        out.append(ev)
    return {"count": len(out), "events": out}


@app.get("/api/nba/live")
def api_nba_live():
    """Análisis en vivo de partidos NBA con detector de sobre-reacción y valor in-play (+EV)."""
    from .model import nba_live
    return nba_live.analyze_live_nba()


@app.get("/api/senior-report")
def api_senior_report(include_5y: bool = True):
    """Reporte cuantitativo completo siguiendo el protocolo de Analista Senior (5 temporadas, Log Loss, Brier, Incertidumbre y Riesgos)."""
    from .model import senior_analyst
    return senior_analyst.generate_senior_report(include_5y=include_5y)


@app.get("/api/tools/historical-5y")
def api_historical_5y(force: bool = False):
    """Ingesta de las últimas 5 temporadas de football-data.co.uk con Log Loss y Brier Score de cierre."""
    from .model import senior_analyst
    return senior_analyst.compute_5y_historical_benchmark(force=force)


@app.get("/api/leagues/{div}/teams")
def api_league_teams(div: str):
    if div not in config.LEAGUES:
        raise HTTPException(404, "Liga no soportada")
    meta = config.LEAGUES[div]
    if meta["kind"] == "intl":
        from .sources import espn, wplay
        evs = espn.fetch_upcoming_events(div, days_ahead=6)
        tset = {t for e in evs for t in (e["home"], e["away"])}
        if not tset:
            wmap = wplay.fetch_division_odds(div, [])
            tset = {t for (h, a) in wmap for t in (h, a)}
        return {"div": div, "league": meta, "mu_home": 1.40, "mu_away": 1.18,
                "uses_xg": True, "teams": sorted(tset), "ratings": []}
    r, current = service.ratings_for(div)
    if not r:
        return {"div": div, "teams": [], "ratings": []}
    rows = []
    as_of = service.now_utc()
    from .model.ratings import team_profile
    for t in r.teams:
        prof = team_profile(t, current, as_of)
        rows.append({
            "team": t,
            "att": round(r.att.get(t, 1.0), 3),
            "defn": round(r.defn.get(t, 1.0), 3),
            "power": round(r.att.get(t, 1.0) / max(r.defn.get(t, 1.0), 0.2), 3),
            "played": prof.get("played", 0),
            "xg_for": prof.get("xg_for"),
            "xg_against": prof.get("xg_against"),
            "xg_diff": prof.get("xg_diff"),
            "goals_for": prof.get("goals_for"),
            "goals_against": prof.get("goals_against"),
            "form": prof.get("form", []),
        })
    rows.sort(key=lambda x: x["power"], reverse=True)
    return {
        "div": div,
        "league": config.LEAGUES[div],
        "mu_home": round(r.mu_home, 3),
        "mu_away": round(r.mu_away, 3),
        "uses_xg": r.uses_xg,
        "teams": r.teams,
        "ratings": rows,
    }


@app.post("/api/matchup")
def api_matchup(req: MatchupRequest):
    if req.div not in config.LEAGUES:
        raise HTTPException(400, "Liga inválida")
    if req.home == req.away:
        raise HTTPException(400, "El equipo local y visitante deben ser distintos")
    try:
        return service.matchup(req.div, req.home, req.away, req.odds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/run")
def api_run():
    return service.run_daily(force=True)


@app.get("/api/history")
def api_history():
    service.settle_open()
    return service.history()


@app.post("/api/picks")
def api_add_pick(req: PickCreateRequest):
    match = {
        "id": req.match_id or f"{req.div}-manual-{req.home}-{req.away}",
        "div": req.div,
        "kickoff": req.kickoff or service.now_utc().isoformat(),
        "home": req.home,
        "away": req.away,
    }
    sel = {
        "market": req.market,
        "selection": req.selection,
        "line": req.line,
        "name": req.name,
        "odds": req.odds,
        "p_model": req.p_model,
        "p_market": req.p_market,
        "p_real": req.p_real,
        "stake_pct": req.stake_pct,
        "stake_amount": req.stake_amount,
        "odds_source": req.bookmaker or "Casa en Colombia",
    }
    added = db.add_pick(match, sel, source="manual", odds=req.odds,
                        stake_amount=req.stake_amount, bookmaker=req.bookmaker)
    return {"ok": True, "added": added}


@app.delete("/api/picks/{pick_id}")
def api_delete_pick(pick_id: int):
    db.delete_pick(pick_id)
    return {"ok": True}


@app.get("/api/backtest")
def api_backtest(basis: str = "avg"):
    if basis not in ("avg", "best"):
        basis = "avg"
    return service.backtest(basis=basis)


@app.get("/api/settings")
def api_get_settings():
    return db.get_settings()


@app.post("/api/settings")
def api_save_settings(payload: dict[str, Any]):
    saved = db.save_settings(payload)
    service._analysis_cache["ts"] = 0
    return saved


# --------------------------------------------------------------------------- #
# Archivos estáticos del Frontend
# --------------------------------------------------------------------------- #
config.FRONTEND_DIR.mkdir(exist_ok=True)


@app.get("/")
def index():
    idx = config.FRONTEND_DIR / "index.html"
    if not idx.exists():
        return JSONResponse({"status": "QuantBet API running"})
    return FileResponse(idx, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")
