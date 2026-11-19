"""Descarga datos de Yahoo Finance con yfinance y genera data/market.json.

Uso:  python scripts/fetch_data.py --out data/market.json [--prev snapshot_anterior.json]

Si una serie falla, se reintenta 3 veces. Si aun así falla y existe un snapshot
anterior, se conserva el dato anterior de esa serie y se marca como "no actualizada".
"""
import argparse, json, math, os, sys, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SERIES = {
    "USD/MXN": {"symbol": "USDMXN=X", "kind": "fx", "desc": "Dólar estadounidense / peso mexicano"},
    "EUR/MXN": {"symbol": "EURMXN=X", "kind": "fx", "desc": "Euro / peso mexicano"},
    "CAD/MXN": {"symbol": "CADMXN=X", "kind": "fx", "desc": "Dólar canadiense / peso mexicano"},
    "EUR/USD": {"symbol": "EURUSD=X", "kind": "fx", "desc": "Euro / dólar (USD/EUR = 1 / EUR/USD)"},
    "irx": {"symbol": "^IRX", "kind": "rate", "desc": "Tasa del T-bill de EE. UU. a 13 semanas (%)"},
    "evz": {"symbol": "^EVZ", "kind": "vol", "optional": True, "desc": "Volatilidad implícita EUR/USD de Cboe (%), opcional"},
}
LIMITS = {"fx": (0.05, 100.0), "rate": (0.0, 30.0), "vol": (0.5, 100.0)}
PERIOD = os.environ.get("PERIOD", "2y")


def fetch_rows(symbol, period):
    if os.environ.get("MOCK_YF"):  # solo para pruebas sin red
        return mock_rows(symbol)
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False, actions=False)
    if df is None or df.empty:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError("Yahoo no devolvió precios")
    close = df["Close"]
    if hasattr(close, "columns"):  # yf.download puede devolver columnas múltiples
        close = close.iloc[:, 0]
    rows = {}
    for ts, v in close.items():
        if v is None or not math.isfinite(float(v)):
            continue
        rows[ts.strftime("%Y-%m-%d")] = round(float(v), 6)
    return sorted(rows.items())


def mock_rows(symbol):
    import random
    rnd = random.Random(symbol)
    base = {"USDMXN=X": 18.4, "EURMXN=X": 21.3, "CADMXN=X": 13.2, "EURUSD=X": 1.16, "^IRX": 3.9, "^EVZ": 7.2}[symbol]
    if os.environ.get("MOCK_FAIL") and symbol in os.environ["MOCK_FAIL"].split(","):
        raise RuntimeError("fallo simulado")
    out, p, d = [], base, datetime(2024, 11, 18)
    from datetime import timedelta
    for _ in range(730):
        d += timedelta(days=1)
        if d.weekday() >= 5:
            continue
        p *= 1 + rnd.gauss(0, 0.006)
        out.append((d.strftime("%Y-%m-%d"), round(p, 6)))
    return out


def fetch_with_retry(key, meta, period, tries=3):
    last = None
    for i in range(tries):
        try:
            rows = fetch_rows(meta["symbol"], period)
            lo, hi = LIMITS[meta["kind"]]
            rows = [(d, c) for d, c in rows if lo < c < hi]
            if len(rows) < (60 if meta["kind"] == "fx" else 1):
                raise RuntimeError(f"solo {len(rows)} datos válidos")
            return rows, None, i + 1
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:300]
            time.sleep(3 * (i + 1))
    return None, last, tries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/market.json")
    ap.add_argument("--prev", default=None)
    a = ap.parse_args()

    prev = {}
    if a.prev and os.path.exists(a.prev):
        try:
            prev = json.load(open(a.prev, encoding="utf-8")).get("series", {})
        except Exception:  # noqa: BLE001
            prev = {}

    try:
        import yfinance
        yfv = yfinance.__version__
    except Exception:  # noqa: BLE001
        yfv = "mock" if os.environ.get("MOCK_YF") else "no instalado"

    started = datetime.now(timezone.utc)
    series, ok = {}, 0
    for key, meta in SERIES.items():
        rows, err, attempts = fetch_with_retry(key, meta, PERIOD)
        entry = {"symbol": meta["symbol"], "desc": meta["desc"], "kind": meta["kind"], "optional": bool(meta.get("optional")), "attempts": attempts}
        if rows:
            ok += 1
            entry.update(ok=True, updated=True, error=None, rows=rows)
        else:
            old = prev.get(key) or {}
            entry.update(ok=False, error=err, rows=old.get("rows", []),
                         updated=False, kept_previous=bool(old.get("rows")),
                         previous_query=old.get("queried_at_utc"))
        if entry["rows"]:
            entry["last_date"], entry["last"] = entry["rows"][-1]
            entry["n"] = len(entry["rows"])
        entry["queried_at_utc"] = started.isoformat(timespec="seconds") if entry["ok"] else (prev.get(key) or {}).get("queried_at_utc")
        series[key] = entry
        status = "OK" if entry["ok"] else ("FALLÓ (se conserva el dato anterior)" if entry.get("kept_previous") else "FALLÓ")
        print(f"{key:8s} {meta['symbol']:10s} {status:38s} {entry.get('n', 0):4d} datos  último {entry.get('last_date', '-')} {entry.get('last', '')} {err or ''}")

    finished = datetime.now(timezone.utc)
    mx = finished.astimezone(ZoneInfo("America/Mexico_City"))
    snap = {
        "schema": 1,
        "source": f"Yahoo Finance vía yfinance {yfv}",
        "generated_at_utc": finished.isoformat(timespec="seconds"),
        "generated_at_mx": mx.strftime("%d/%m/%Y %H:%M:%S"),
        "duration_s": round((finished - started).total_seconds(), 1),
        "period": PERIOD,
        "ok_count": ok,
        "total": len(SERIES),
        "complete": all(e["ok"] for e in series.values() if not e["optional"]),
        "required_ok": sum(1 for e in series.values() if e["ok"] and not e["optional"]),
        "required_total": sum(1 for e in series.values() if not e["optional"]),
        "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                    if os.environ.get("GITHUB_RUN_ID") else None),
        "trigger": os.environ.get("GITHUB_EVENT_NAME", "manual"),
        "series": series,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nConsulta terminada {snap['generated_at_mx']} (CDMX): {ok} de {len(SERIES)} series correctas -> {a.out}")

    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(f"### Snapshot de mercado: {ok} de {len(SERIES)} series correctas\n\nGenerado {snap['generated_at_mx']} (hora CDMX) con {snap['source']}.\n\n")
            f.write("| Serie | Símbolo | Estado | Último dato | Valor | Error |\n|---|---|---|---|---|---|\n")
            for k, e in series.items():
                f.write(f"| {k} | {e['symbol']} | {'OK' if e['ok'] else 'Falló'} | {e.get('last_date', '-')} | {e.get('last', '-')} | {e['error'] or ''} |\n")

    fx_missing = [k for k, e in series.items() if e["kind"] == "fx" and not e["rows"]]
    if fx_missing:
        print("ERROR: no hay datos para " + ", ".join(fx_missing), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
