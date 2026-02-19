'use strict';

// ── State ────────────────────────────────────────────────────────
const state = {
  view:         'library', // 'library' | <playlist_id>
  tracks:       [],        // currently displayed tracks
  playlists:    [],        // sidebar list
  queue:        [],        // playback queue
  queueIndex:   -1,
  currentTrack: null,
  isPlaying:    false,
};

// ── DOM refs ─────────────────────────────────────────────────────
const audio        = document.getElementById('audio');
const tbody        = document.getElementById('track-tbody');
const plList       = document.getElementById('playlist-list');
const searchInput  = document.getElementById('search-input');
const btnClear     = document.getElementById('btn-clear-search');
const trackCount   = document.getElementById('track-count');
const emptyState   = document.getElementById('empty-state');
const npTitle      = document.getElementById('np-title');
const npArtist     = document.getElementById('np-artist');
const npArt        = document.getElementById('np-art');
const btnPlay      = document.getElementById('btn-play');
const btnPrev      = document.getElementById('btn-prev');
const btnNext      = document.getElementById('btn-next');
const seekBar      = document.getElementById('seek-bar');
const volBar       = document.getElementById('vol-bar');
const npCur        = document.getElementById('np-cur');
const npDur        = document.getElementById('np-dur');
const ctxMenu      = document.getElementById('ctx-menu');
const ctxMenuList  = document.getElementById('ctx-menu-list');
const toast        = document.getElementById('toast');
const scanPath     = document.getElementById('scan-path');
const btnScan      = document.getElementById('btn-scan');
const scanStatus   = document.getElementById('scan-status');
const btnNewPl     = document.getElementById('btn-new-playlist');

// ── Utilities ────────────────────────────────────────────────────

function fmtDur(secs) {
  if (!secs || isNaN(secs)) return '—';
  const m = Math.floor(secs / 60);
  const s = String(Math.floor(secs % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let toastTimer;
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2800);
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ── API helpers ──────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api' + path, opts);
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(txt);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Library & playlist loading ───────────────────────────────────

async function loadLibrary(q = '') {
  state.view = 'library';
  const params = q ? `?q=${encodeURIComponent(q)}` : '';
  try {
    state.tracks = await api('GET', `/library${params}`);
  } catch (e) {
    state.tracks = [];
  }
  renderTracks(state.tracks, { showRemove: false });
  updateActiveNav();
}

async function loadPlaylist(id) {
  state.view = id;
  try {
    const pl = await api('GET', `/playlists/${id}`);
    state.tracks = pl.tracks;
    renderTracks(state.tracks, { showRemove: true, playlistId: id });
  } catch (e) {
    state.tracks = [];
    renderTracks([], {});
  }
  updateActiveNav();
}

async function loadPlaylists() {
  try {
    state.playlists = await api('GET', '/playlists');
  } catch (e) {
    state.playlists = [];
  }
  renderPlaylists();
}

// ── Render: playlists sidebar ─────────────────────────────────────

function renderPlaylists() {
  plList.innerHTML = '';
  state.playlists.forEach(pl => {
    const li = document.createElement('li');
    li.className = 'pl-item' + (state.view === pl.id ? ' active' : '');
    li.dataset.plId = pl.id;
    li.innerHTML = `
      <span class="pl-name" title="${esc(pl.name)}">${esc(pl.name)}</span>
      <button class="btn-del-pl" title="Delete playlist">✕</button>
    `;
    li.querySelector('.pl-name').addEventListener('click', () => loadPlaylist(pl.id));
    li.querySelector('.btn-del-pl').addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm(`Delete playlist "${pl.name}"?`)) return;
      await api('DELETE', `/playlists/${pl.id}`);
      if (state.view === pl.id) await loadLibrary();
      await loadPlaylists();
    });
    plList.appendChild(li);
  });
}

function updateActiveNav() {
  document.querySelectorAll('.nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.view === 'library' && state.view === 'library')
  );
  document.querySelectorAll('.pl-item').forEach(el =>
    el.classList.toggle('active', Number(el.dataset.plId) === state.view)
  );
}

// ── Render: track table ──────────────────────────────────────────

function renderTracks(tracks, { showRemove = false, playlistId = null } = {}) {
  tbody.innerHTML = '';
  const isEmpty = tracks.length === 0;
  emptyState.classList.toggle('hidden', !isEmpty);
  document.getElementById('track-table').classList.toggle('hidden', isEmpty);
  trackCount.textContent = isEmpty ? '' : `${tracks.length} track${tracks.length !== 1 ? 's' : ''}`;

  tracks.forEach((track, i) => {
    const tr = document.createElement('tr');
    tr.dataset.trackId = track.id;
    if (state.currentTrack?.id === track.id) tr.classList.add('playing');

    tr.innerHTML = `
      <td class="col-num">
        <span class="playing-icon">♪</span>
        <span class="row-num">${i + 1}</span>
      </td>
      <td class="col-art">
        <img class="art-thumb" src="/api/tracks/${track.id}/artwork"
             alt="" onerror="this.style.visibility='hidden'" />
      </td>
      <td class="col-title">${esc(track.title || track.path?.split('/').pop() || '—')}</td>
      <td class="col-artist">${esc(track.artist || '—')}</td>
      <td class="col-album">${esc(track.album || '—')}</td>
      <td class="col-year">${esc(track.year || '—')}</td>
      <td class="col-dur">${fmtDur(track.duration_secs)}</td>
      <td class="col-actions">
        <button class="btn-row btn-add" title="Add to playlist">+</button>
        ${showRemove ? `<button class="btn-row btn-rm" title="Remove from playlist">✕</button>` : ''}
      </td>
    `;

    // Double-click → play track, set queue to current visible list
    tr.addEventListener('dblclick', () => {
      playTrack(track, tracks, i);
    });

    // Add to playlist button
    tr.querySelector('.btn-add').addEventListener('click', e => {
      e.stopPropagation();
      showAddMenu(track, e.currentTarget);
    });

    // Remove from playlist button
    if (showRemove) {
      tr.querySelector('.btn-rm').addEventListener('click', async e => {
        e.stopPropagation();
        await api('DELETE', `/playlists/${playlistId}/tracks/${track.id}`);
        showToast('Removed from playlist');
        await loadPlaylist(playlistId);
      });
    }

    tbody.appendChild(tr);
  });
}

function highlightCurrentRow() {
  document.querySelectorAll('#track-tbody tr').forEach(tr => {
    tr.classList.toggle('playing', Number(tr.dataset.trackId) === state.currentTrack?.id);
  });
}

// ── Add-to-playlist context menu ──────────────────────────────────

function showAddMenu(track, anchor) {
  closeCtxMenu();

  ctxMenuList.innerHTML = state.playlists.length
    ? state.playlists.map(pl =>
        `<div class="ctx-item" data-pl-id="${pl.id}">${esc(pl.name)}</div>`
      ).join('')
    : `<div class="ctx-empty">No playlists yet — create one first</div>`;

  const rect = anchor.getBoundingClientRect();
  // Position so menu doesn't overflow viewport
  const menuW = 190;
  let left = rect.right - menuW;
  if (left < 8) left = 8;
  const top = Math.min(rect.bottom + 4, window.innerHeight - 200);

  ctxMenu.style.top  = `${top}px`;
  ctxMenu.style.left = `${left}px`;
  ctxMenu.classList.remove('hidden');

  ctxMenuList.querySelectorAll('.ctx-item').forEach(item => {
    item.addEventListener('click', async () => {
      const plId = Number(item.dataset.plId);
      try {
        await api('POST', `/playlists/${plId}/tracks`, { track_id: track.id });
        const pl = state.playlists.find(p => p.id === plId);
        showToast(`Added to "${pl?.name ?? 'playlist'}"`);
      } catch (e) {
        showToast('Already in that playlist or error');
      }
      closeCtxMenu();
    });
  });

  setTimeout(() => document.addEventListener('click', closeCtxMenu, { once: true }), 0);
}

function closeCtxMenu() {
  ctxMenu.classList.add('hidden');
}

// ── Playback ─────────────────────────────────────────────────────

function playTrack(track, queue = null, index = 0) {
  state.currentTrack = track;
  state.queue        = queue ? [...queue] : [track];
  state.queueIndex   = index;

  audio.src = `/api/tracks/${track.id}/stream`;
  audio.volume = volBar.value / 100;
  audio.play().catch(() => {});

  state.isPlaying = true;
  updateNowPlaying();
  highlightCurrentRow();
}

function updateNowPlaying() {
  const t = state.currentTrack;
  if (!t) return;

  npTitle.textContent  = t.title  || t.path?.split('/').pop() || '—';
  npArtist.textContent = t.artist || '—';
  btnPlay.textContent  = state.isPlaying ? '⏸' : '▶';
  btnPlay.style.fontSize = state.isPlaying ? '20px' : '26px';

  if (t.has_artwork) {
    npArt.src = `/api/tracks/${t.id}/artwork`;
    npArt.style.visibility = 'visible';
  } else {
    npArt.src = '';
    npArt.style.visibility = 'hidden';
  }
}

function playNext() {
  if (!state.queue.length) return;
  state.queueIndex = (state.queueIndex + 1) % state.queue.length;
  playTrack(state.queue[state.queueIndex], state.queue, state.queueIndex);
}

function playPrev() {
  if (!state.queue.length) return;
  // If more than 3 seconds in, restart current track
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  state.queueIndex = (state.queueIndex - 1 + state.queue.length) % state.queue.length;
  playTrack(state.queue[state.queueIndex], state.queue, state.queueIndex);
}

// ── Audio events ─────────────────────────────────────────────────

audio.addEventListener('timeupdate', () => {
  if (!audio.duration) return;
  seekBar.value = Math.round((audio.currentTime / audio.duration) * 1000);
  npCur.textContent = fmtDur(audio.currentTime);
});

audio.addEventListener('loadedmetadata', () => {
  npDur.textContent = fmtDur(audio.duration);
});

audio.addEventListener('ended', playNext);

audio.addEventListener('play',  () => {
  state.isPlaying = true;
  btnPlay.textContent = '⏸';
  btnPlay.style.fontSize = '20px';
});

audio.addEventListener('pause', () => {
  state.isPlaying = false;
  btnPlay.textContent = '▶';
  btnPlay.style.fontSize = '26px';
});

// ── Control events ────────────────────────────────────────────────

btnPlay.addEventListener('click', () => {
  if (!state.currentTrack) return;
  state.isPlaying ? audio.pause() : audio.play();
});

btnNext.addEventListener('click', playNext);
btnPrev.addEventListener('click', playPrev);

seekBar.addEventListener('input', () => {
  if (audio.duration) {
    audio.currentTime = (seekBar.value / 1000) * audio.duration;
  }
});

volBar.addEventListener('input', () => {
  audio.volume = volBar.value / 100;
});

// ── Search ────────────────────────────────────────────────────────

const doSearch = debounce(async () => {
  const q = searchInput.value.trim();
  btnClear.classList.toggle('visible', q.length > 0);
  if (state.view === 'library') {
    await loadLibrary(q);
  } else {
    // Filter loaded playlist tracks client-side
    const lower = q.toLowerCase();
    const filtered = state.tracks.filter(t =>
      (t.title  || '').toLowerCase().includes(lower) ||
      (t.artist || '').toLowerCase().includes(lower) ||
      (t.album  || '').toLowerCase().includes(lower)
    );
    renderTracks(filtered, { showRemove: false });
  }
}, 300);

searchInput.addEventListener('input', doSearch);

btnClear.addEventListener('click', () => {
  searchInput.value = '';
  btnClear.classList.remove('visible');
  if (state.view === 'library') loadLibrary();
  else loadPlaylist(state.view);
});

// ── Sidebar: library nav ──────────────────────────────────────────

document.querySelector('.nav-item[data-view="library"]').addEventListener('click', () => {
  searchInput.value = '';
  btnClear.classList.remove('visible');
  loadLibrary();
});

// ── Playlist creation ─────────────────────────────────────────────

btnNewPl.addEventListener('click', async () => {
  const name = prompt('New playlist name:');
  if (!name?.trim()) return;
  await api('POST', '/playlists', { name: name.trim() });
  await loadPlaylists();
  showToast(`Playlist "${name.trim()}" created`);
});

// ── Scan ──────────────────────────────────────────────────────────

btnScan.addEventListener('click', async () => {
  const path = scanPath.value.trim();
  if (!path) { showToast('Enter a directory path first'); return; }

  btnScan.disabled = true;
  scanStatus.textContent = 'Scanning…';

  try {
    const res = await api('POST', '/library/scan', { path });
    scanStatus.textContent = `✓ Indexed ${res.indexed} file${res.indexed !== 1 ? 's' : ''}`;
    if (state.view === 'library') await loadLibrary(searchInput.value.trim());
  } catch (e) {
    scanStatus.textContent = `Error: ${e.message}`;
  } finally {
    btnScan.disabled = false;
  }
});

// ── Keyboard shortcuts ────────────────────────────────────────────

document.addEventListener('keydown', e => {
  // Space = play/pause (unless typing in an input)
  if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    if (state.currentTrack) state.isPlaying ? audio.pause() : audio.play();
  }
  if (e.code === 'ArrowRight' && e.altKey) { e.preventDefault(); playNext(); }
  if (e.code === 'ArrowLeft'  && e.altKey) { e.preventDefault(); playPrev(); }
});

// ── Init ──────────────────────────────────────────────────────────

(async function init() {
  audio.volume = volBar.value / 100;
  await Promise.all([loadPlaylists(), loadLibrary()]);
})();
