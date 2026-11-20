# Asesor de futuros FX: versión gestión de riesgos

App en un solo HTML (`index.html`) para analizar futuros de divisas (USD/MXN, EUR/MXN, CAD/MXN, EUR/USD, USD/EUR):
payoff, margin account, vector de P&L, VaR/ES, cobertura con opciones, optimizador, mercado, backtesting, estrés y tablero de riesgo.

## Cómo llegan los datos de Yahoo Finance
1. `scripts/fetch_data.py` consulta Yahoo con **yfinance** (4 tipos de cambio, `^IRX` y `^EVZ`, 2 años diarios).
2. Escribe `data/market.json` con la hora de la consulta (UTC y CDMX), cuántas series salieron bien y el error de las que fallaron.
   Si una serie falla, se conserva su dato de la consulta anterior y se marca como no actualizada.
3. GitHub Actions (`.github/workflows/actualizar-datos.yml`) corre el script **cada 20 minutos en días hábiles**, una vez al día en fin de semana,
   en cada `push` y cuando alguien pulsa **Run workflow**. Luego publica la app y el JSON en GitHub Pages.
4. La app lee `data/market.json` al abrir y con el botón **Actualizar datos**. Si no lo encuentra, intenta Yahoo directo y al final usa los datos incrustados.

## Puesta en marcha (una sola vez)
1. Crear un repositorio **público** en GitHub y subir todos estos archivos (incluida la carpeta oculta `.github`).
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Actions → "Actualizar datos y publicar" → **Run workflow**. En 1–2 minutos queda el link:
   `https://<usuario>.github.io/<repositorio>/`

## Forzar una consulta nueva
Actions → "Actualizar datos y publicar" → Run workflow (o el botón "Generar consulta nueva" dentro de la pestaña Mercado,
que lleva ahí). Solo pueden hacerlo los colaboradores del repositorio. El resumen de cada ejecución muestra la tabla de series.

## Opcional: que el botón "Actualizar datos" lance una consulta nueva
Sin esto, el botón relee la consulta más reciente (máximo 20 minutos de antigüedad en días hábiles).
Para que cualquier visitante pueda pedir una consulta en ese momento:
1. GitHub → Settings → Developer settings → Fine-grained tokens → nuevo token solo para este repositorio,
   permiso **Actions: Read and write**.
2. Cloudflare → Workers → Create → pegar `worker-trigger.js`. En Settings → Variables agregar
   `GH_TOKEN` (secreto, el token), `REPO` = `mauolivajacuinde-hue/asesor-futuros-fx`,
   `ALLOWED_ORIGIN` = `https://mauolivajacuinde-hue.github.io`.
3. En el repositorio: Settings → Secrets and variables → Actions → Variables → `TRIGGER_URL` = la URL del Worker.
4. Correr el workflow una vez. Desde ahí el botón pide la consulta, espera 1–2 minutos y carga los datos solo.
El token nunca llega a la página; el Worker limita a una consulta cada 3 minutos.

## Notas
- Yahoo Finance no tiene API oficial; yfinance se instala en su última versión en cada ejecución para seguir sus cambios.
- GitHub pausa los workflows programados si el repositorio pasa 60 días sin actividad; se reactivan con un push o un Run workflow.
- Herramienta académica; no es asesoría financiera.
