"""Public live-tracking PAGE (Share Links, F22).

A login-less HTML page served at ``GET /track/{token}`` — the human-facing counterpart
to the JSON ``GET /api/v1/share/{token}`` endpoint. This is what a share recipient opens
in any browser: a Leaflet/OSM map (keyless, matching the rest of the stack) that polls
the public JSON API client-side and renders the child's first name + live location only
(Decision D10 — never history/battery/device).

Security: the page is a **static shell** — the token is read from the URL by the page's
own JS (never injected server-side), so there is no reflected-XSS surface. All auth /
rate-limit / expiry handling lives in the JSON endpoint the page calls. Multi-language:
the page reads ``?lang=en|hi|ar`` and pulls the same public i18n bundle the apps use,
applying ``track.*`` keys (Arabic ⇒ RTL).
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["share"])

# Self-contained page. No server-side interpolation of the token (read from the path in
# JS) so there's nothing to escape. Leaflet + OSM tiles from CDN, izyLrn-branded shell.
_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>izyLrn — Live tracking</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<style>
  :root { --cyan:#16AFF0; --indigo:#2C56EE; --violet:#6609E3; --ink:#161335; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:var(--ink); }
  #app { display:flex; flex-direction:column; height:100%; }
  header {
    display:flex; align-items:center; gap:10px; padding:12px 16px; color:#fff;
    background:linear-gradient(120deg,var(--indigo),var(--violet));
  }
  header .brand { font-weight:800; font-size:17px; letter-spacing:.2px; }
  header .brand .cy { color:#8fe3ff; }
  header .who { margin-left:auto; font-size:13px; opacity:.95; text-align:end; }
  #map { flex:1; background:#eef2fb; }
  .bar {
    padding:10px 16px; font-size:13px; color:#4b5563; background:#fff;
    border-top:1px solid #eef0f6; display:flex; gap:10px; align-items:center; flex-wrap:wrap;
  }
  .dot { height:9px; width:9px; border-radius:50%; background:#16A34A; display:inline-block; }
  .dot.stale { background:#9ca3af; }
  .center {
    flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
    text-align:center; padding:32px; gap:12px; color:#4b5563;
  }
  .center h2 { color:var(--ink); margin:0; font-size:18px; }
  .spinner {
    height:34px; width:34px; border:3px solid #dbe3f7; border-top-color:var(--indigo);
    border-radius:50%; animation:spin 1s linear infinite;
  }
  @keyframes spin { to { transform:rotate(360deg); } }
  [dir="rtl"] header .who { text-align:start; }
</style>
</head>
<body>
<div id="app">
  <header>
    <span class="brand">izy<span class="cy">Lrn</span></span>
    <span class="who" id="who"></span>
  </header>
  <div id="map" style="display:none"></div>
  <div class="bar" id="bar" style="display:none">
    <span class="dot" id="dot"></span>
    <span id="status"></span>
    <span id="expiry" style="margin-inline-start:auto"></span>
  </div>
  <div class="center" id="state">
    <div class="spinner"></div>
    <div id="stateText">Loading…</div>
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(function () {
  var token = decodeURIComponent((location.pathname.split('/').filter(Boolean).pop() || ''));
  var lang = (new URLSearchParams(location.search).get('lang') || 'en').toLowerCase();
  if (['en','hi','ar'].indexOf(lang) < 0) lang = 'en';
  if (lang === 'ar') document.documentElement.setAttribute('dir', 'rtl');
  document.documentElement.setAttribute('lang', lang);

  // Baseline English strings; overridden by the i18n bundle (track.* keys) when it loads.
  var T = {
    'track.tracking': 'Tracking', 'track.loading': 'Loading…',
    'track.waiting': "Waiting for a location fix…",
    'track.updated': 'Updated', 'track.just_now': 'just now',
    'track.min_ago': 'min ago', 'track.hr_ago': 'h ago',
    'track.expires': 'Link expires', 'track.expired_title': 'Link expired',
    'track.expired': 'This tracking link is invalid or has expired.',
    'track.busy': 'Too many requests — please wait a moment.',
    'track.error': "Couldn't load tracking right now.",
    'track.no_location': 'No location shared yet.'
  };
  function t(k) { return T[k] || k; }

  var map, marker, timer;
  var $ = function (id) { return document.getElementById(id); };

  function showState(text) {
    $('map').style.display = 'none'; $('bar').style.display = 'none';
    $('state').style.display = 'flex';
    $('state').innerHTML = '<h2>' + text + '</h2>';
  }
  function showMap() {
    $('state').style.display = 'none';
    $('map').style.display = 'block'; $('bar').style.display = 'flex';
    if (!map) {
      map = L.map('map', { zoomControl: true }).setView([20.5937, 78.9629], 4);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '© OpenStreetMap'
      }).addTo(map);
    }
  }
  function ago(ts) {
    if (!ts) return '';
    var secs = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
    if (secs < 60) return t('track.just_now');
    if (secs < 3600) return Math.floor(secs / 60) + ' ' + t('track.min_ago');
    return Math.floor(secs / 3600) + ' ' + t('track.hr_ago');
  }
  function fmtTime(ts) {
    try { return new Date(ts).toLocaleString(lang); } catch (e) { return ''; }
  }

  function render(d) {
    $('who').textContent = t('track.tracking') + ' ' + (d.child_name || '');
    var loc = d.location;
    if (!loc || loc.lat == null || loc.lng == null) {
      showState(t('track.waiting'));
      return;
    }
    showMap();
    var ll = [loc.lat, loc.lng];
    if (!marker) { marker = L.marker(ll).addTo(map); map.setView(ll, 16); }
    else { marker.setLatLng(ll); map.panTo(ll); }
    var fresh = loc.timestamp && (Date.now() - new Date(loc.timestamp).getTime() < 300000);
    $('dot').className = 'dot' + (fresh ? '' : ' stale');
    $('status').textContent = t('track.updated') + ' ' + ago(loc.timestamp);
    $('expiry').textContent = t('track.expires') + ': ' + fmtTime(d.expires_at);
  }

  function poll() {
    fetch('/api/v1/share/' + encodeURIComponent(token), { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (r.status === 404) { stop(); showState(t('track.expired')); throw 'stop'; }
        if (r.status === 429) { showState(t('track.busy')); throw 'skip'; }
        if (!r.ok) { throw 'err'; }
        return r.json();
      })
      .then(function (body) { render(body.data || body); })
      .catch(function (e) { if (e !== 'stop' && e !== 'skip' && !map) showState(t('track.error')); });
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  // Pull the i18n bundle for the requested language, then start polling.
  fetch('/api/v1/i18n/' + lang)
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (body) {
      var m = body && (body.data || body);
      if (m) { for (var k in T) { if (m[k]) T[k] = m[k]; } }
    })
    .catch(function () {})
    .finally(function () {
      if (!token) { showState(t('track.expired')); return; }
      poll();
      timer = setInterval(poll, 15000);
    });
})();
</script>
</body>
</html>
"""


@router.get("/track/{token}", response_class=HTMLResponse, include_in_schema=False)
async def public_track_page(token: str) -> HTMLResponse:
    """Serve the login-less live-tracking page. Static shell — the token is read from
    the URL client-side and resolved against the public JSON API; no DB access here."""
    return HTMLResponse(content=_PAGE)
