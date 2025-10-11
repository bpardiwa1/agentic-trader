# Scripts — Run & Operate the Bots

This guide shows **how to start each asset bot** and **how to interact with the FastAPI service** to run trades (manually or automatically).

> These scripts assume Windows + PowerShell and MetaTrader 5 installed. The API server defaults to port `8001` (configurable via env).

---

## 1) One‑time setup

1. **Install requirements** (ideally in a venv):

    ```powershell
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

2. **Set your MT5 live credentials** in `app/env/core.env`:

    ```ini
    EXECUTION_MODE=live
    BROKER_BACKEND=mt5

    MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
    MT5_LOGIN=YOUR_LOGIN
    MT5_PASSWORD=YOUR_PASSWORD
    MT5_SERVER=VTMarkets-Live 3

    # Optional (leave as-is unless you need to change):
    PORT=8001
    AGENT_TIMEFRAME=M15
    AGENT_PERIOD_SEC=60
    ```

3. **Choose symbols per asset** in their respective env files under `app/env/`:

    - `fx.env` → `AGENT_SYMBOLS=EURUSD-ECNc`
    - `xau.env` → `AGENT_SYMBOLS=XAUUSD-ECNc`
    - `indices.env` → `AGENT_SYMBOLS=US30-ECN,NAS100-ECN,GER40-ECN`
    - `equities.env` → `AGENT_SYMBOLS=MSFT,NVDA`

    Make sure the **symbol aliases** are set as well (already populated in the envs we provided).

---

## 2) Start a bot

From the repository root (`agentic-trader\`), run:

```powershell
# Forex
.pp\scripts
un_agent.ps1 FX

# Gold (XAUUSD)
.pp\scripts
un_agent.ps1 XAU

# Indices (US30, NAS100, GER40, …)
.pp\scripts
un_agent.ps1 INDICES

# Equities (stocks)
.pp\scripts
un_agent.ps1 EQUITIES
```

Each command:

-   Loads `app/env/core.env` and the matching asset env (e.g., `app/env/fx.env`).
-   Starts FastAPI on the configured `PORT` (default 8001).
-   Connects to MT5 and enters the agent loop (decide → guardrails → execute).

> To run **multiple assets in parallel**, open multiple PowerShell windows and start each asset bot in its own window.

---

## 3) Check health / logs

-   **Health endpoint** (should return `{ "status": "ok" }` when ready):

    ```powershell
    curl http://localhost:8001/health
    ```

-   **Tail logs** (replace with your log path if different):
    ```powershell
    Get-Content -Path .\logs\server.log -Wait
    ```

---

## 4) Manually trigger a decision (optional)

Force the agent to evaluate a symbol _now_ via the `agents/decide` endpoint. Example for **Gold**:

```powershell
$body = @{
  symbol   = "XAUUSD-ECNc"
  timeframe= "M15"
  strategy = "XAU_MOMENTUM"  # or MOMENTUM / INDICES_MOMENTUM / EQUITIES_MOMENTUM
} | ConvertTo-Json

curl -Method POST `
     -Uri http://localhost:8001/agents/decide `
     -ContentType "application/json" `
     -Body $body
```

You’ll get a JSON with either **no-trade** reason or a **signal** (side/SL/TP/size_hint). If guardrails pass and the risk engine approves, the bot will place the order via MT5.

---

## 5) Place a market order directly (power users)

If you want to bypass the strategy and **place an order directly** through the API (use carefully in live!):

```powershell
$body = @{
  symbol  = "XAUUSD-ECNc"
  side    = "LONG"     # or "SHORT"
  lots    = 0.05
  sl_pips = 200
  tp_pips = 300
  comment = "manual-test"
} | ConvertTo-Json

curl -Method POST `
     -Uri http://localhost:8001/orders/market `
     -ContentType "application/json" `
     -Body $body
```

The response contains `retcode`, `status`, and `raw.deal/order` fields from MT5.

---

## 6) Useful tips

-   **Live vs Demo**: determined by the MT5 account you log into **and** `EXECUTION_MODE=live` in `core.env`.
-   **Agent cadence**: `AGENT_PERIOD_SEC` controls how often the loop wakes (default 60s).
-   **Warmup data**: ensure enough bars are available; our strategies require ~100 bars (see `MIN_BARS` in each strategy).
-   **Guardrails**: see `app/risk/guards.py` and env limits (cooldowns, exposure caps, daily loss limit).
-   **Trailing stops**: controlled via `TRAIL_*` settings in `core.env`.

---

## 7) Troubleshooting

-   **No ticks / price**: symbol may not be visible → open it in MT5 Market Watch or ensure `symbol_select` succeeds.
-   **Rejected “not enough data”**: increase history warmup or ensure market is open.
-   **Lot sizing off**: check `LOT_MODE`, `RISK_PCT`, per-symbol `LOTS_*`, and account currency/precision.
-   **Pylance warnings** about MT5 attributes: our executor uses a typeless `mt5: Any` shim to support dynamic MT5 API fields.

---

## 8) Stopping bots

Press **Ctrl + C** in the PowerShell window to gracefully stop the FastAPI server and the agent loop.

---

**Happy trading!** If you want auto-start for all assets, create separate shortcuts or add a small `run_all.ps1` that starts each in a new window.

# Scripts README

## Start a single bot

powershell -ExecutionPolicy Bypass -File app\scripts\run_agent.ps1 -Asset FX
powershell -ExecutionPolicy Bypass -File app\scripts\run_agent.ps1 -Asset XAU
powershell -ExecutionPolicy Bypass -File app\scripts\run_agent.ps1 -Asset INDICES
powershell -ExecutionPolicy Bypass -File app\scripts\run_agent.ps1 -Asset EQUITIES

## Start all bots

powershell -ExecutionPolicy Bypass -File app\scripts\run_all.ps1

The script loads `app/env/core.env` then the per-asset env.
