// 이제 뭐 하지? 프로토타입 프론트엔드 (해시 라우팅, 빌드 없음)
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const app = $('#app');
const TILE_STYLE = 'https://tiles.openfreemap.org/styles/liberty';
// 지도 색을 디자인 시안(파스텔, 선 없음)에 맞춤: OpenFreeMap liberty 를 받아 레이어 색만 바꾼다. 지도 자체 POI 는 숨겨 추천 핀만 보이게.
const MAP_COLORS = { bg: '#F5FAF6', water: '#DCEEFA', green: '#E4F1DA', building: '#ECF0EE', road: '#FFFFFF', minor: '#FBFDFC', rail: '#D9E1E4', text: '#56636C' };
function pastel(map) {
  const C = MAP_COLORS;
  for (const l of map.getStyle().layers) {
    const sl = l['source-layer'] || '', id = l.id, set = (k, v) => { try { map.setPaintProperty(id, k, v); } catch (e) {} };
    const hide = () => map.setLayoutProperty(id, 'visibility', 'none');
    if (l.type === 'background') set('background-color', C.bg);
    else if (l.type === 'raster' || sl === 'aeroway' || sl === 'aerodrome_label' || sl === 'poi' || id.includes('shield') || id.includes('one_way')) hide();
    else if (l.type === 'fill') {
      if (sl === 'water') set('fill-color', C.water);
      else if (sl === 'park' || (sl === 'landcover' && /wood|grass|forest|scrub/.test(id)) || (sl === 'landuse' && /park|cemetery|grass|pitch/.test(id))) { set('fill-color', C.green); set('fill-opacity', 1); set('fill-outline-color', C.green); }
      else if (sl === 'building') { set('fill-color', C.building); set('fill-outline-color', C.building); }
      else { set('fill-color', C.bg); set('fill-outline-color', C.bg); }
    } else if (l.type === 'fill-extrusion') hide();
    else if (l.type === 'line') {
      if (sl === 'waterway') set('line-color', C.water);
      else if (sl === 'boundary' || sl === 'park') hide();
      else if (sl === 'transportation') {
        if (/casing|tunnel/.test(id)) hide();
        else if (/rail|transit|subway/.test(id)) { set('line-color', C.rail); set('line-dasharray', [1, 0]); }
        else set('line-color', /minor|service|path|track|pedestrian/.test(id) ? C.minor : C.road);
      }
    } else if (l.type === 'symbol') { set('text-color', C.text); set('text-halo-color', '#FFFFFF'); set('text-halo-width', 1.5); set('icon-opacity', 0); }
  }
}
// 좌표들이 모두 보이게 맞춤: 핀 이름표 폭·하단 카드 높이만큼 여백, 너무 붙은 경우엔 줌 상한
function fitTo(map, pts, pad = {}) {
  const valid = pts.filter(p => p && p.lat != null);
  if (!valid.length) return;
  const b = new maplibregl.LngLatBounds(); valid.forEach(p => b.extend([p.lon, p.lat]));
  const run = () => { map.resize(); map.fitBounds(b, { padding: { top: 90, bottom: 60, left: 70, right: 70, ...pad }, maxZoom: 15.5, duration: 0 }); };
  map.loaded() ? run() : map.once('load', run);
}
function newMap(opts) { const m = new maplibregl.Map({ style: TILE_STYLE, attributionControl: { compact: true }, ...opts }); m.on('style.load', () => pastel(m)); return m; }
const THEMES = [['famous', '유명 명소'], ['local', '현지인 인기'], ['known', '한국인 인기'], ['hidden', '숨은 명소']];
// 월별 명소 칩: 서버가 일본 날짜로 정함 (1~7일 지난달+이번 달, 8~23일 이번 달, 24일~ 이번 달+다음 달)
const CATS = [['meal', '식사'], ['cafe', '카페'], ['bar', '술'], ['sight', '구경'], ['walk', '산책, 자연'], ['shop', '쇼핑'], ['rest', '휴식']];
const S = { loc: null, current: null, last: null, busy: false };   // loc: 브라우저 GPS(서버엔 요청 때만 보냄)
S.seasonMonths = [new Date().getMonth() + 1];

async function api(path, opt = {}) {
  const r = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opt,
    body: opt.body ? JSON.stringify(opt.body) : undefined });
  if (r.status === 401) { location.hash = '#/start'; throw new Error('login'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || '오류가 났어요');
  return j;
}
// 화면 반응 로그 (지도 열기·핀·길찾기·공유·위키) → reaction_logs. 실패해도 화면엔 영향 없음
const logUi = (type, place_id, props) => api('/api/log', { method: 'POST', body: { type, place_id, props } }).catch(() => {});
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add('hidden'), 2200); }
const dist = m => m == null ? '' : m < 1000 ? `${m}m` : `${(m / 1000).toFixed(1)}km`;
const time = ts => new Date(ts * 1000).toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
S.mode = localStorage.getItem('locMode') || 'gps';   // gps | manual (역 이름으로 정하면 GPS 를 보내지 않음)
const withLoc = b => S.loc && S.mode === 'gps' ? { ...b, lat: S.loc.lat, lon: S.loc.lon } : b;

function watchLocation() {
  if (!navigator.geolocation || S._watch) return;
  S._watch = navigator.geolocation.watchPosition(p => { S.loc = { lat: p.coords.latitude, lon: p.coords.longitude }; },
    () => {}, { enableHighAccuracy: true, maximumAge: 30000 });
}

const header = (right = '') => `
<header class="sticky top-0 z-40 bg-canvas/90 backdrop-blur-xl border-b border-slate-200/60">
  <div class="h-16 px-5 flex items-center justify-between">
    <h1 class="font-head text-[20px] cursor-pointer" onclick="location.hash='#/chat'">이제 뭐 하지?</h1>
    <div class="flex items-center gap-2">${right}
      <button onclick="location.hash='#/me'" class="w-9 h-9 rounded-full bg-leaf flex items-center justify-center"><span class="material-symbols-outlined text-white text-[18px]">person</span></button>
    </div></div></header>`;
const nav = active => `
<nav class="fixed bottom-0 inset-x-0 z-40 pb-safe bg-white/95 backdrop-blur-xl border-t border-slate-100">
  <div class="flex justify-around items-center h-16 max-w-[430px] mx-auto">
    ${[['chat', 'chat_bubble', '여행챗'], ['saved', 'bookmark_heart', '저장목록']].map(([k, i, l]) => `
    <a href="#/${k}" class="flex flex-col items-center gap-1 ${active === k ? 'text-leaf font-head' : 'text-slate-400'}">
      <span class="material-symbols-outlined ${active === k ? 'fill' : ''}">${i}</span><span class="text-[12px]">${l}</span></a>`).join('')}
  </div></nav>`;
const chipBtn = (label, onclick, on = false) =>
  `<button onclick="${onclick}" class="text-[13px] px-3.5 py-1.5 rounded-full whitespace-nowrap shrink-0 active:scale-95 transition ${on ? 'bg-leaf text-white' : 'bg-leafbg text-[#3B533E] border border-leafline'}">${esc(label)}</button>`;

// ---------- 시작 (로그인) ----------
// Google 로그인 버튼: 브랜드 가이드라인(라이트 테마) — 공식 4색 G 로고, Roboto Medium, 흰 배경 + #747775 테두리, 글자 #1F1F1F
const GOOGLE_G = `<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>`;
const GOOGLE_BTN = `<a href="/auth/google/login" aria-label="Google 계정으로 계속하기"
  class="flex items-center justify-center gap-2.5 w-full h-[52px] mb-3 rounded-full bg-white border border-[#747775] text-[#1F1F1F] active:bg-[#F2F2F2]"
  style="font-family:Roboto,Arial,sans-serif;font-weight:500;font-size:15px;letter-spacing:.25px">${GOOGLE_G}<span>Google 계정으로 계속하기</span></a>`;
async function viewStart() {
  const cfg = await fetch('/api/auth/config').then(r => r.json()).catch(() => ({}));
  app.innerHTML = `
  <div class="min-h-screen flex flex-col justify-end px-6 pb-12">
    <div class="text-center mb-10"><h1 class="font-head text-[34px]">이제 뭐 하지?</h1><p class="text-slate-500 mt-2">P들을 위한 일본 여행 챗봇</p></div>
    ${cfg.google ? GOOGLE_BTN : ''}
    <button id="guest" class="w-full h-[52px] bg-leaf text-white rounded-full font-head">게스트로 시작하기</button>
    <p class="text-[12px] text-slate-500 text-center mt-5 leading-relaxed">시작하면 만 14세 이상이며
      <a class="underline" href="/static/legal/terms.html">이용약관</a> 및 <a class="underline" href="/static/legal/privacy.html">개인정보 처리방침</a>에 동의하는 것으로 봅니다.<br>
      로그인 ID와 추천 기록만 저장해요. 이메일은 받지 않아요.</p>
  </div>`;
  $('#guest').onclick = async () => { await api('/api/auth/guest', { method: 'POST' }); location.hash = '#/chat'; };
}

// ---------- 여행챗 ----------
function bubble(m) {
  if (m.role === 'user') return `<div class="flex flex-col items-end max-w-[85%] ml-auto"><div class="p-3.5 rounded-2xl rounded-tr-md bg-leaf text-white">${esc(m.text)}</div>
    <span class="text-[11px] mt-1 mr-1 text-slate-400">${m.at ? time(m.at) : ''}</span></div>`;
  let h = m.text ? `<div class="flex flex-col items-start max-w-[85%]"><div class="p-3.5 rounded-2xl rounded-tl-md bg-white shadow-sm border border-slate-100">${esc(m.text)}</div>
    <span class="text-[11px] mt-1 ml-1 text-slate-400">${m.at ? time(m.at) : ''}</span></div>` : '';
  if (m.need_location) h += `<button onclick="askLocation()" class="self-start text-[13px] px-3.5 py-1.5 rounded-full bg-leafbg border border-leafline">위치 설정하기</button>`;
  if (m.summary) {
    h += `<div class="w-full bg-white shadow-sm border border-slate-100 rounded-2xl p-4 flex items-center justify-between">
      <div><h3 class="font-head text-[18px]">${esc(m.summary || '')}</h3>${(m.notes || []).filter(n => n.includes('넓혔')).map(n => `<p class="text-[12px] text-slate-500 mt-1">${esc(n)}</p>`).join('')}</div>
      ${m.cards.length ? `<button onclick='openMap(${JSON.stringify(m.cards).replace(/'/g, "&#39;")})' class="flex items-center gap-1 text-coral text-[13px] font-bold bg-coralbg px-3.5 py-1.5 rounded-full border border-[#f5d5cf] shrink-0">지도에서 볼래요<span class="material-symbols-outlined text-[18px]">arrow_forward</span></button>` : ''}</div>
      <div class="flex gap-2 overflow-x-auto pb-1 -mx-5 px-5">${m.cards.map(c => `
        <div data-place="${esc(c.id)}" class="w-44 shrink-0 rounded-2xl px-3.5 py-3 bg-white shadow-sm border border-slate-100 cursor-pointer active:scale-[.98] transition">
          ${c.tags && c.tags.length ? `<span class="text-[11px] px-2 py-0.5 rounded-full font-bold bg-coralbg text-coral">${esc(c.tags[0])}</span>` : ''}
          <h4 class="font-head text-[17px] truncate mt-1">${esc(c.name)}</h4>
          ${c.name_ja ? `<p class="text-[11px] text-slate-400 truncate">${esc(c.name_ja)}</p>` : ''}
          <p class="text-[12px] truncate mt-1.5 text-slate-500">${dist(c.distance_m)} · ${esc(c.kind)}</p></div>`).join('')}</div>`;
  }
  return h;
}
async function viewChat() {
  watchLocation();
  try { S.seasonMonths = (await api('/api/season-months')).months; } catch (e) {}
  app.innerHTML = header() + `
  <main class="px-5 pb-44">
    <div class="flex justify-end pt-3 pb-4"><button onclick="askLocation()" class="flex items-center gap-1 px-3.5 py-1.5 rounded-full bg-leafbg border border-leafline text-leaf">
      <span class="material-symbols-outlined fill text-[18px]">location_on</span><span id="curname" class="text-[13px] font-bold">위치 설정</span></button></div>
    <div id="stream" class="flex flex-col gap-3"></div>
  </main>
  <div class="fixed bottom-16 inset-x-0 z-30 bg-gradient-to-t from-canvas via-canvas to-transparent pt-4 pb-2">
    <div class="max-w-[430px] mx-auto px-5">
      <div class="flex items-center gap-1.5 overflow-x-auto pb-2 -mx-5 px-5">
        ${S.seasonMonths.map(m => chipBtn(`${m}월 명소`, `chip(null,'season',${m})`)).join('')}${THEMES.map(([k, l]) => chipBtn(l, `chip(null,'${k}')`)).join('')}${CATS.map(([k, l]) => chipBtn(l, `chip('${k}',null)`)).join('')}</div>
      <form id="f" class="flex items-center gap-2">
        <input id="q" autocomplete="off" maxlength="300" class="flex-1 bg-white shadow-sm border border-slate-200 rounded-full px-5 py-3 focus:outline-none" placeholder="먹고 싶은 걸 말해 주세요">
        <button class="w-11 h-11 rounded-full flex items-center justify-center bg-leaf text-white shrink-0"><span class="material-symbols-outlined">arrow_upward</span></button>
      </form></div></div>` + nav('chat');
  const msgs = await api('/api/messages');
  const stream = $('#stream');
  stream.innerHTML = bubble({ role: 'assistant', text: 'いらっしゃいませ! 오늘은 뭐가 당기세요?' }) + msgs.map(bubble).join('');
  const lastCur = [...msgs].reverse().find(m => m.current);
  if (S.me?.current) setCur(S.me.current); else if (lastCur) setCur(lastCur.current);
  ensureLocation();
  scrollDown();
  $('#f').onsubmit = e => { e.preventDefault(); const v = $('#q').value.trim(); if (v) { $('#q').value = ''; send('/api/chat', withLoc({ message: v }), v); } };
}
function setCur(c) { S.current = c; const el = $('#curname'); if (el && c) el.textContent = c.name; }
function scrollDown() { setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 50); }
async function send(path, body, userText) {
  if (S.busy) return; S.busy = true;
  const stream = $('#stream');
  stream.insertAdjacentHTML('beforeend', bubble({ role: 'user', text: userText, at: Date.now() / 1000 }) + `<div id="typing" class="text-slate-400 text-sm">고르는 중…</div>`);
  scrollDown();
  try {
    const r = await api(path, { method: 'POST', body });
    $('#typing')?.remove();
    stream.insertAdjacentHTML('beforeend', bubble({ role: 'assistant', text: r.reply, at: Date.now() / 1000, ...r }));
    if (r.current) setCur(r.current);
    S.last = r.cards;
  } catch (e) { $('#typing')?.remove(); toast(e.message); }
  S.busy = false; scrollDown();
}
window.chip = (category, theme, month) => {
  const label = category ? CATS.find(c => c[0] === category)[1] : theme === 'season' ? `${month}월 명소` : THEMES.find(t => t[0] === theme)[1];
  send('/api/recommend', withLoc({ category, theme, month }), label);
};
// ---------- 여행 시작 위치 (GPS 를 못 쓰거나 일본 밖일 때 자동으로 뜸) ----------
function closeSheet() { $('#startsheet')?.remove(); }
async function pickStart(p) {
  try {
    const r = await api('/api/location', { method: 'POST', body: { lat: p.lat, lon: p.lon, name: p.name } });
    S.mode = 'manual'; localStorage.setItem('locMode', 'manual'); setCur(r.current); closeSheet();
    $('#stream')?.insertAdjacentHTML('beforeend', bubble({ role: 'assistant', text: `${r.current.name}에서 시작할게요! 뭐 할까요?`, at: Date.now() / 1000 }));
    scrollDown();
  } catch (e) { toast(e.message); }
}
async function useGps() {
  if (!navigator.geolocation) return toast('이 브라우저는 위치를 지원하지 않아요');
  navigator.geolocation.getCurrentPosition(async pos => {
    S.loc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    try { const r = await api('/api/location', { method: 'POST', body: S.loc }); S.mode = 'gps'; localStorage.setItem('locMode', 'gps'); setCur(r.current); closeSheet(); toast('현재 위치로 설정했어요'); }
    catch (e) { toast(e.message); }
  }, () => toast('위치 권한이 꺼져 있어요'), { enableHighAccuracy: true, timeout: 8000 });
}
async function openStartSheet() {
  closeSheet();
  const starts = await api('/api/geo/starts');
  const row = (p, i) => `<button data-i="${i}" class="pick w-full flex items-center gap-3 px-2 py-3 rounded-2xl hover:bg-canvas text-left">
      <span class="material-symbols-outlined text-leaf">${p.kind === '공항' ? 'flight_land' : p.kind === '역' ? 'train' : 'location_on'}</span>
      <span class="flex-1 min-w-0"><span class="block font-head text-[17px] truncate">${esc(p.name)}</span>
      <span class="block text-[12px] text-slate-500 truncate">${esc([p.kind, p.sub || p.city].filter(Boolean).join(' · '))}</span></span></button>`;
  document.body.insertAdjacentHTML('beforeend', `
  <div id="startsheet" class="fixed inset-0 z-[70] bg-black/30 flex items-end justify-center">
    <div class="w-full max-w-[430px] bg-white rounded-t-[28px] px-5 pt-3 pb-6 max-h-[85vh] flex flex-col">
      <div class="w-9 h-1 rounded-full bg-slate-200 mx-auto mb-4"></div>
      <h2 class="font-head text-[22px]">어디에서 여행을 시작할 거예요?</h2>
      <p class="text-[13px] text-slate-500 mt-1">도착하는 공항을 고르거나, 역·장소 이름으로 찾아보세요</p>
      <input id="ss" autocomplete="off" maxlength="100" placeholder="예: 교토역, 난바, 삿포로" class="w-full mt-4 bg-canvas border border-slate-200 rounded-full px-5 py-3 focus:outline-none">
      ${navigator.geolocation ? `<button id="gps" class="mt-3 flex items-center gap-2 text-[14px] text-leaf px-2"><span class="material-symbols-outlined fill text-[20px]">my_location</span>지금 위치 사용 (일본에 있을 때)</button>` : ''}
      <p id="sslabel" class="text-[12px] text-slate-400 mt-4 mb-1 px-2">주요 공항</p>
      <div id="sslist" class="overflow-y-auto -mx-2 px-2 flex-1"></div>
    </div></div>`);
  let shown = starts;
  const render = (list, label) => { shown = list; $('#sslabel').textContent = label;
    $('#sslist').innerHTML = list.length ? list.map(row).join('') : `<p class="text-center text-slate-400 py-8">찾는 곳이 없어요</p>`; };
  render(starts, '주요 공항');
  $('#sslist').onclick = e => { const b = e.target.closest('.pick'); if (b) pickStart(shown[+b.dataset.i]); };
  $('#gps') && ($('#gps').onclick = useGps);
  $('#startsheet').onclick = e => { if (e.target.id === 'startsheet' && S.current) closeSheet(); };   // 위치가 정해진 뒤에만 바깥 눌러 닫기
  let t;
  $('#ss').oninput = e => { clearTimeout(t); const q = e.target.value.trim();
    if (!q) return render(starts, '주요 공항');
    t = setTimeout(async () => render(await api('/api/geo/search?q=' + encodeURIComponent(q)), '검색 결과'), 250); };
}
window.askLocation = openStartSheet;
// 처음 들어왔을 때 위치가 없으면: GPS 를 시도하고, 거부·실패·일본 밖이면 시작 위치 창을 띄운다
function ensureLocation() {
  if (S.current) return;
  if (!navigator.geolocation || S.mode === 'manual') return openStartSheet();
  navigator.geolocation.getCurrentPosition(async pos => {
    S.loc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    try { const r = await api('/api/location', { method: 'POST', body: S.loc }); setCur(r.current); }
    catch (e) { openStartSheet(); }            // 일본 밖 (대부분의 테스트 사용자)
  }, () => openStartSheet(), { timeout: 6000, maximumAge: 60000 });
}

// ---------- 지도 ----------
window.openMap = cards => { S.last = cards; logUi('map_open'); location.hash = '#/map'; };
function viewMap() {
  const cards = S.last || [];
  app.innerHTML = header() + `
  <div class="relative" style="height:calc(100vh - 64px - 64px)">
    <div id="map" class="absolute inset-0"></div>
    <button onclick="history.back()" class="absolute top-4 left-4 w-11 h-11 rounded-full bg-white shadow flex items-center justify-center"><span class="material-symbols-outlined">arrow_back_ios_new</span></button>
    <div id="sheet" class="absolute bottom-4 left-4 right-4"></div>
  </div>` + nav('chat');
  if (!cards.length) return;
  const center = S.current || cards[0];
  const map = newMap({ container: 'map', center: [center.lon, center.lat], zoom: 14 });
  fitTo(map, [...cards, S.current], { bottom: 190 });   // 하단 카드 높이만큼
  if (S.current) { const d = document.createElement('div'); d.className = 'me'; new maplibregl.Marker({ element: d }).setLngLat([S.current.lon, S.current.lat]).addTo(map); }
  const pins = cards.map((c, i) => {
    const el = document.createElement('div'); el.className = 'pin'; el.innerHTML = `${esc(c.name)}<small>${dist(c.distance_m)}</small>`;
    el.onclick = () => { select(i); logUi('pin_click', c.id, { rank: i + 1 }); };
    new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([c.lon, c.lat]).addTo(map); return el;
  });
  function select(i) {
    pins.forEach((p, j) => p.classList.toggle('on', i === j));
    const c = cards[i];
    $('#sheet').innerHTML = `<div data-place="${esc(c.id)}" class="bg-white rounded-3xl shadow-lg p-5 cursor-pointer">
      <div class="flex items-center gap-2 text-[13px] text-slate-500"><span class="bg-leafbg px-2.5 py-0.5 rounded-full text-leaf">${dist(c.distance_m)}</span>${esc(c.kind)}${c.tags.length ? ' · ' + esc(c.tags.join(' · ')) : ''}</div>
      <h3 class="font-head text-[22px] mt-1.5">${esc(c.name)}</h3>${c.name_ja ? `<p class="text-[12px] text-slate-400">${esc(c.name_ja)}</p>` : ''}
      <p class="text-[13px] text-slate-500 mt-1">눌러서 자세히 보기</p></div>`;
  }
  select(0);
}

// ---------- 장소 카드 ----------
async function viewPlace(id) {
  // 거리 계산용 현재 위치는 소수 2자리(약 1km)로만 보냄: 주소창 값은 서버 접속 로그에 남으므로 정확한 좌표를 넣지 않음
  const q = S.loc && S.mode === 'gps' ? `?lat=${S.loc.lat.toFixed(2)}&lon=${S.loc.lon.toFixed(2)}` : '';
  const p = await api(`/api/places/${encodeURIComponent(id)}${q}`);
  app.innerHTML = header(`<button onclick="sharePlace()" class="w-9 h-9 flex items-center justify-center text-slate-600"><span class="material-symbols-outlined">share</span></button>`) + `
  <div class="relative h-[38vh]"><div id="map" class="absolute inset-0"></div>
    <button onclick="history.back()" class="absolute top-4 left-4 w-11 h-11 rounded-full bg-white shadow flex items-center justify-center"><span class="material-symbols-outlined">arrow_back_ios_new</span></button></div>
  <section class="relative -mt-7 bg-white rounded-t-[28px] px-6 pt-3 pb-40 min-h-[62vh]">
    <div class="w-9 h-1 rounded-full bg-slate-200 mx-auto mb-5"></div>
    ${p.image ? `<img src="${esc(p.image)}" class="w-full h-44 object-cover rounded-2xl mb-4" loading="lazy" onerror="this.remove()">` : ''}
    <h2 class="font-head text-[30px] leading-tight">${esc(p.name)}</h2>${p.name_ja ? `<p class="text-slate-400">${esc(p.name_ja)}</p>` : ''}
    <p class="text-slate-500 mt-2">${esc(p.kind)}${p.distance_m != null ? ' · ' + dist(p.distance_m) : ''}</p>
    <div class="flex flex-wrap gap-1.5 mt-3">${p.distance_m != null && p.distance_m < 500 ? `<span class="bg-leafbg text-leaf text-[13px] px-3 py-1 rounded-full">🚶 가까움</span>` : ''}
      ${p.tags.map(t => `<span class="bg-coralbg text-coral text-[13px] px-3 py-1 rounded-full">${esc(t)}</span>`).join('')}${p.visited ? `<span class="bg-slate-100 text-slate-500 text-[13px] px-3 py-1 rounded-full">방문함</span>` : ''}</div>
    ${p.description ? `<div class="mt-4 bg-canvas rounded-2xl p-4">${esc(p.description)}</div>
      <div class="flex justify-between text-[12px] text-slate-500 mt-2"><span>출처: ${esc(p.description_source)}</span>${p.wiki_url ? `<a class="underline" target="_blank" rel="noopener" data-log="wiki_open" data-id="${esc(id)}" href="${esc(p.wiki_url)}">위키백과 ↗</a>` : ''}</div>` : ''}
    <p class="text-[11px] text-slate-400 mt-4">데이터: ${esc(p.sources.join(' · '))} · 정보는 실제와 다를 수 있어요</p>
    <button id="go" class="w-full mt-6 bg-leaf text-white rounded-full py-4 font-head text-[18px] flex items-center justify-center gap-2 ${p.visited ? 'opacity-50' : ''}"><span class="material-symbols-outlined">near_me</span>여기로 갈까요?</button>
    <div class="flex justify-center gap-10 mt-4 text-slate-600">
      <button id="save" class="flex items-center gap-1.5"><span class="material-symbols-outlined ${p.saved ? 'fill text-coral' : ''}">favorite</span>${p.saved ? '저장됨' : '저장'}</button>
      <button id="skip" class="flex items-center gap-1.5"><span class="material-symbols-outlined">close</span>여기 말고</button></div>
  </section>` + nav('chat');
  const map = newMap({ container: 'map', center: [p.lon, p.lat], zoom: 15 });
  // 현재 위치가 3km 안이면 둘 다 보이게, 멀면 장소만
  if (S.current && p.distance_m != null && p.distance_m < 3000) {
    const d = document.createElement('div'); d.className = 'me'; new maplibregl.Marker({ element: d }).setLngLat([S.current.lon, S.current.lat]).addTo(map);
    fitTo(map, [p, S.current], { top: 80, bottom: 50 });
  }
  const el = document.createElement('div'); el.className = 'pin on'; el.innerHTML = `${esc(p.name)}<small>${dist(p.distance_m)}</small>`;
  new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lon, p.lat]).addTo(map);
  window.sharePlace = () => { logUi('share', id); const u = `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}`;
    navigator.share ? navigator.share({ title: p.name, url: u }).catch(() => {}) : (navigator.clipboard.writeText(u), toast('링크를 복사했어요')); };
  $('#go').onclick = async () => {
    if (!p.visited) { const r = await api(`/api/places/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: { event: 'select' } }); S.current = r.current; }
    logUi('directions_open', id); window.open(p.directions, '_blank'); toast('방문 목록에 담았어요'); location.hash = '#/chat';
  };
  $('#save').onclick = async () => { await api(`/api/places/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: { event: p.saved ? 'unsave' : 'save' } }); viewPlace(id); };
  $('#skip').onclick = async () => { await api(`/api/places/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: { event: 'skip' } }); toast('다음엔 덜 보여드릴게요'); history.back(); };
}

// ---------- 저장목록 ----------
async function viewSaved(tab = 'visited', filter = '') {
  const L = await api('/api/me/lists');
  const list = (L[tab] || []).filter(x => !filter || x.name.includes(filter) || (x.kind || '').includes(filter));
  const stars = x => [1, 2, 3, 4, 5].map(n => `<span onclick="event.stopPropagation();rate('${x.visit_id}',${n})" class="material-symbols-outlined text-[22px] cursor-pointer ${x.rating >= n ? 'fill text-coral' : 'text-slate-300'}">star</span>`).join('');
  const rated = L.visited.filter(x => x.rating);
  app.innerHTML = header() + `
  <main class="px-5 pt-4 pb-28">
    <div class="flex bg-leafbg rounded-full p-1">${[['visited', '내가 간 곳'], ['saved', '가고 싶은 곳']].map(([k, l]) => `
      <button onclick="viewSaved('${k}')" class="flex-1 rounded-full py-2.5 font-head ${tab === k ? 'bg-leaf text-white' : 'text-slate-500'}">${l} <span class="text-[12px] opacity-80">${L[k].length}</span></button>`).join('')}</div>
    <input id="sf" maxlength="100" value="${esc(filter)}" placeholder="식당, 카페, 명소 검색…" class="w-full mt-4 bg-white border border-slate-200 rounded-full px-5 py-3 focus:outline-none">
    ${tab === 'visited' && rated.length ? `<div class="mt-4 bg-leafbg/60 rounded-2xl px-4 py-3 text-[14px]">방문 ${L.visited.length}곳 (평균 ★ ${(rated.reduce((a, x) => a + x.rating, 0) / rated.length).toFixed(1)})</div>` : ''}
    <div class="flex flex-col gap-3 mt-4">${list.length ? list.map(x => `
      <div ${x.id ? `data-place="${esc(x.id)}"` : ''} class="bg-white rounded-2xl shadow-sm border border-slate-100 p-4 cursor-pointer">
        <div class="flex items-center gap-2"><h3 class="font-head text-[18px] truncate">${esc(x.name)}</h3>
          ${tab === 'visited' ? `<span class="text-[11px] px-2 py-0.5 rounded-full ${x.footprint ? 'bg-leafbg text-leaf' : 'bg-slate-100 text-slate-500'}">${x.footprint ? '발자국' : '방문완료'}</span>` : ''}</div>
        <p class="text-[13px] text-slate-500 mt-1">${esc(x.kind)}${x.visited_at ? ' · ' + new Date(x.visited_at * 1000).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' }) + (x.trip_day ? ` · ${x.trip_day}일차` : '') : ''}</p>
        ${tab === 'visited' ? `<div class="flex items-center justify-between mt-3 pt-3 border-t border-slate-100"><div>${stars(x)}</div>
          <div class="flex gap-1">${(x.tags || []).slice(0, 2).map(t => `<span class="text-[11px] bg-slate-100 px-2 py-0.5 rounded-full">${esc(t)}</span>`).join('')}</div></div>` : ''}
      </div>`).join('') : `<p class="text-center text-slate-400 py-10">아직 없어요</p>`}</div>
    ${tab === 'visited' ? `<div class="mt-6 bg-leafbg/60 rounded-2xl p-5 text-center"><p class="text-[14px]">목록에 없는 나만의 스팟도 바로 기록해보세요</p>
      <button onclick="addSpot()" class="mt-3 bg-leaf text-white rounded-full px-6 py-2.5 font-head">+ 직접 등록하기</button></div>` : ''}
  </main>` + nav('saved');
  $('#sf').onchange = e => viewSaved(tab, e.target.value.trim());
  S.tab = tab;
}
window.viewSaved = viewSaved;
window.logUi = logUi;
window.rate = async (vid, n) => { await api(`/api/me/visits/${vid}`, { method: 'PATCH', body: { rating: n } }); viewSaved(S.tab || 'visited'); };
window.addSpot = async () => {
  const name = prompt('어떤 곳이에요? (예: 가모가와 강변 벤치)'); if (!name) return;
  const pos = S.loc || S.current; if (!pos) return toast('위치를 먼저 켜 주세요');
  await api('/api/me/spots', { method: 'POST', body: { name, lat: pos.lat, lon: pos.lon } }); toast('발자국을 남겼어요'); viewSaved('visited');
};

// ---------- 내 정보 ----------
async function viewMe() {
  const me = await api('/api/me');
  app.innerHTML = header() + `
  <main class="px-5 pt-6 pb-28 flex flex-col gap-3">
    <div class="bg-white rounded-2xl p-5 shadow-sm">${me.google ? 'Google 계정으로 로그인됨' : '게스트로 이용 중 (마지막 이용 30일 뒤 기록 삭제)'}</div>
    <button id="endtrip" class="bg-white rounded-2xl p-4 shadow-sm text-left">여행 끝내기 <span class="text-slate-400 text-[13px]">— 방문 목록을 비우고 새 여행 시작</span></button>
    <a href="/static/legal/sources.html" class="bg-white rounded-2xl p-4 shadow-sm">데이터 출처 및 라이선스</a>
    <a href="/static/legal/terms.html" class="bg-white rounded-2xl p-4 shadow-sm">이용약관</a>
    <a href="/static/legal/privacy.html" class="bg-white rounded-2xl p-4 shadow-sm">개인정보 처리방침</a>
    <button id="logout" class="bg-white rounded-2xl p-4 shadow-sm text-left">로그아웃</button>
    <button id="bye" class="text-coral text-[13px] mt-4">탈퇴하고 기록 모두 삭제</button>
  </main>` + nav('');
  $('#endtrip').onclick = async () => { if (confirm('여행을 끝낼까요? 방문 목록이 비워져요.')) { await api('/api/trips/end', { method: 'POST' }); toast('새 여행을 시작해요'); location.hash = '#/chat'; } };
  $('#logout').onclick = async () => { await api('/api/auth/logout', { method: 'POST' }); location.hash = '#/start'; };
  $('#bye').onclick = async () => { if (confirm('모든 기록이 바로 삭제돼요. 탈퇴할까요?')) { await api('/api/me', { method: 'DELETE' }); location.hash = '#/start'; } };
}

// ---------- 라우터 ----------
async function route() {
  const h = location.hash || '#/chat';
  try {
    if (h === '#/start') return viewStart();
    S.me = await api('/api/me');
    if (h.startsWith('#/place/')) return viewPlace(decodeURIComponent(h.slice(8)));
    if (h === '#/map') return viewMap();
    if (h === '#/saved') return viewSaved();
    if (h === '#/me') return viewMe();
    return viewChat();
  } catch (e) { if (e.message !== 'login') toast(e.message); }
}
window.addEventListener('hashchange', () => { window.scrollTo(0, 0); route(); });
// 장소 카드·목록 클릭 (id 를 onclick 문자열에 넣지 않고 data 속성으로: 따옴표가 든 값이 스크립트가 되지 않게)
document.addEventListener('click', e => {
  const log = e.target.closest('[data-log]');
  if (log) logUi(log.dataset.log, log.dataset.id);
  const pl = e.target.closest('[data-place]');
  if (pl) location.hash = '#/place/' + encodeURIComponent(pl.dataset.place);
});
route();
