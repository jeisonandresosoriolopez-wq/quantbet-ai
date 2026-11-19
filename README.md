# 🎯 Opta QuantBet AI — Quantitative Sports Betting Analytics

Sistema cuantitativo avanzado de Value Bets (+EV) para Fútbol y NBA (con cuotas y mercados de referencia en Wplay.co y BetPlay para Colombia).

---

## 🚀 Características Principales

* **Fútbol (Dixon-Coles & Poisson Bivariado):**
  * Modelado de matrices de probabilidad para 1X2, Más/Menos de 2.5 goles, Ambos Equipos Anotan (BTTS) y Hándicap Asiático.
  * Centro de Especiales Opta: Tiros de Esquina, Tiros al Arco (SOT), Faltas Cometidas y Tarjetas Disciplinarias.
  * Cobertura de Grandes Ligas Europeas + Ligas de América (Colombia Liga Betplay, Argentina, Brasil, México, etc.).

* **NBA (Stats Perform & Opta Framework):**
  * Estimación de Ritmo (*Pace*), Offensive/Defensive Ratings y distribución normal para Spreads y Totales.
  * Props de Jugador: Puntos, Rebotes y Asistencias con proyecciones y devig sin margen.
  * **Monitor NBA en Vivo:** Detector automático de Sobre-Reacción (*Pace Overreaction Detector*) con alertas de *Under* inflado y *Hándicaps con colchón*.

* **Gestión de Capital (Bankroll Management):**
  * Criterio Kelly Fraccional (25% Kelly con tope duro del 2% por apuesta).
  * Seguimiento de CLV (*Closing Line Value*) e Historial de Rendimiento.

* **Armador de Boletos Wplay (1-Clic):**
  * Generador de parlays y apuestas sencillas con instrucciones paso a paso para apostar sin riesgo de bloqueo.

---

## 🛠️ Instalación y Ejecución Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/TU_USUARIO/quantbet-ai.git
   cd quantbet-ai
   ```

2. **Crear entorno virtual e instalar dependencias:**
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Iniciar el servidor local:**
   ```bash
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   Abrir en tu navegador: [http://localhost:8000](http://localhost:8000)

---

## ☁️ Despliegue en la Nube (Render.com / Railway)

Este repositorio está listo para despliegue en 1 clic:
* **Render.com:**
  1. Conecta tu repositorio de GitHub en [Render.com](https://render.com).
  2. Selecciona **Web Service** -> Runtime: **Python**.
  3. Build Command: `pip install -r requirements.txt`
  4. Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
  5. ¡Listo! Tu aplicación estará en vivo 24/7 con HTTPS gratuito.
