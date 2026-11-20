// Cloudflare Worker opcional: permite que el botón "Actualizar datos" de la página pública
// lance una consulta nueva de yfinance (workflow_dispatch) sin exponer ningún token.
// Variables del Worker: GH_TOKEN (secreto: token fine-grained con permiso Actions: Read and write
// solo sobre este repositorio), REPO = "mauolivajacuinde-hue/asesor-futuros-fx",
// ALLOWED_ORIGIN = "https://mauolivajacuinde-hue.github.io".
const COOLDOWN_S = 180;

export default {
  async fetch(request, env) {
    const cors = {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    const json = (obj, status) => new Response(JSON.stringify(obj), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (request.method !== 'POST') return json({ ok: false, msg: 'Usa POST' }, 405);

    // Enfriamiento: una consulta cada 3 minutos como máximo.
    const cache = caches.default, key = new Request('https://cooldown.local/' + env.REPO);
    const hit = await cache.match(key);
    if (hit) {
      const left = COOLDOWN_S - Math.floor((Date.now() - Number(await hit.text())) / 1000);
      if (left > 0) return json({ ok: false, cooldown: true, retry_in: left, msg: 'Ya hay una consulta en curso' }, 200);
    }

    const r = await fetch(`https://api.github.com/repos/${env.REPO}/actions/workflows/actualizar-datos.yml/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'asesor-futuros-fx',
      },
      body: JSON.stringify({ ref: 'main' }),
    });
    if (r.status === 204) {
      await cache.put(key, new Response(String(Date.now()), { headers: { 'Cache-Control': `max-age=${COOLDOWN_S}` } }));
      return json({ ok: true, msg: 'Consulta solicitada' }, 200);
    }
    return json({ ok: false, msg: `GitHub respondió ${r.status}` }, 502);
  },
};
