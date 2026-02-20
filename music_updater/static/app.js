'use strict';

// ── State ────────────────────────────────────────────────────────
const state = {
  view:           'library', // 'library' | <playlist_id>
  tracks:         [],        // currently displayed tracks
  playlists:      [],        // sidebar list
  devices:        [],        // detected mount points
  selectedDevice: null,      // { path, label } | null
  queue:          [],        // playback queue
  queueIndex:     -1,
  currentTrack:   null,
  isPlaying:      false,
  shuffle:        false,
  repeat:         false,
  sortKey:        null,      // field name or null
  sortDir:        1,         // 1 = asc, -1 = desc
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
const btnNewPl          = document.getElementById('btn-new-playlist');
const deviceList        = document.getElementById('device-list');
const btnRefreshDevices = document.getElementById('btn-refresh-devices');
const btnFetchArtAll    = document.getElementById('btn-fetch-art-all');
const btnShuffle        = document.getElementById('btn-shuffle');
const btnRepeat         = document.getElementById('btn-repeat');

// Edit modal
const editOverlay      = document.getElementById('edit-overlay');
const editClose        = document.getElementById('edit-close');
const editCancel       = document.getElementById('edit-cancel');
const editSave         = document.getElementById('edit-save');
const editLookupQ      = document.getElementById('edit-lookup-q');
const editLookupBtn    = document.getElementById('edit-lookup-btn');
const editLookupRes    = document.getElementById('edit-lookup-results');
const editTitle        = document.getElementById('edit-title');
const editArtist       = document.getElementById('edit-artist');
const editAlbum        = document.getElementById('edit-album');
const editYear         = document.getElementById('edit-year');
const editTrackNum     = document.getElementById('edit-track');
const editGenre        = document.getElementById('edit-genre');
const editArtFile      = document.getElementById('edit-art-file');
const editArtUploadBtn = document.getElementById('edit-art-upload-btn');

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

// ── Devices ───────────────────────────────────────────────────────

async function loadDevices() {
  try {
    state.devices = await api('GET', '/devices');
  } catch {
    state.devices = [];
  }
  renderDevices();
}

function renderDevices() {
  deviceList.innerHTML = '';

  if (!state.devices.length) {
    const li = document.createElement('li');
    li.className = 'dev-empty';
    li.textContent = 'No devices found';
    deviceList.appendChild(li);
    return;
  }

  state.devices.forEach(dev => {
    const li = document.createElement('li');
    const isSelected = state.selectedDevice?.path === dev.path;
    li.className = 'pl-item' + (isSelected ? ' active' : '');
    li.title = dev.path;
    li.innerHTML = `
      <span style="font-size:13px;flex-shrink:0">💾</span>
      <span class="pl-name">${esc(dev.label)}</span>
    `;
    li.addEventListener('click', () => selectDevice(dev));
    deviceList.appendChild(li);
  });
}

function selectDevice(dev) {
  if (state.selectedDevice?.path === dev.path) {
    state.selectedDevice = null;
    document.body.classList.remove('has-device');
    showToast('Device disconnected');
  } else {
    state.selectedDevice = dev;
    document.body.classList.add('has-device');
    showToast(`Connected: ${dev.label}`);
  }
  renderDevices();
}

async function copyTrackToDevice(track) {
  if (!state.selectedDevice) return;
  try {
    const res = await api('POST', '/devices/copy', {
      track_ids:   [track.id],
      device_path: state.selectedDevice.path,
    });
    if (res.copied === 1) {
      showToast(`Copied to ${state.selectedDevice.label}`);
    } else if (res.skipped === 1) {
      showToast('Already on device — skipped');
    } else {
      showToast(`Copy error: ${res.errors[0]?.reason ?? 'unknown'}`);
    }
  } catch (e) {
    showToast(`Copy failed: ${e.message}`);
  }
}

// ── Edit metadata modal ───────────────────────────────────────────

let editTrack = null;

function openEditModal(track) {
  editTrack = track;
  editTitle.value    = track.title        || '';
  editArtist.value   = track.artist       || '';
  editAlbum.value    = track.album        || '';
  editYear.value     = track.year         || '';
  editTrackNum.value = track.track_number || '';
  editGenre.value    = track.genre        || '';
  // Pre-fill lookup box with best guess for the search
  editLookupQ.value  = [track.artist, track.title].filter(Boolean).join(' ');
  editLookupRes.innerHTML = '';
  editLookupRes.classList.remove('has-results');
  editOverlay.classList.remove('hidden');
  editTitle.focus();
}

function closeEditModal() {
  editOverlay.classList.add('hidden');
  editTrack = null;
}

function populateForm(candidate) {
  if (candidate.title)  editTitle.value    = candidate.title;
  if (candidate.artist) editArtist.value   = candidate.artist;
  if (candidate.album)  editAlbum.value    = candidate.album;
  if (candidate.year)   editYear.value     = candidate.year;
  if (candidate.track)  editTrackNum.value = candidate.track;
  if (candidate.genre)  editGenre.value    = candidate.genre;
  editLookupRes.classList.remove('has-results');
}

async function doLookup() {
  const q = editLookupQ.value.trim();
  if (!q) return;
  editLookupBtn.disabled = true;
  editLookupBtn.textContent = '…';
  try {
    const results = await api('GET', `/library/lookup?q=${encodeURIComponent(q)}`);
    editLookupRes.innerHTML = '';
    if (!results.length) {
      editLookupRes.innerHTML = '<div class="lookup-empty">No results found</div>';
    } else {
      results.forEach(r => {
        const div = document.createElement('div');
        div.className = 'lookup-item';
        div.innerHTML = `
          ${r.artwork_url ? `<img src="${esc(r.artwork_url)}" alt="" onerror="this.style.display='none'" />` : ''}
          <div class="lookup-item-meta">
            <div class="lookup-item-title">${esc(r.title || '—')}</div>
            <div class="lookup-item-sub">${esc(r.artist)}${r.album ? ' · ' + esc(r.album) : ''}${r.year ? ' (' + esc(r.year) + ')' : ''}</div>
          </div>
        `;
        div.addEventListener('click', () => populateForm(r));
        editLookupRes.appendChild(div);
      });
    }
    editLookupRes.classList.add('has-results');
  } catch (e) {
    editLookupRes.innerHTML = `<div class="lookup-empty">Lookup error: ${esc(e.message)}</div>`;
    editLookupRes.classList.add('has-results');
  } finally {
    editLookupBtn.disabled = false;
    editLookupBtn.textContent = 'Search';
  }
}

async function saveEdit() {
  if (!editTrack) return;
  editSave.disabled = true;
  try {
    await api('PUT', `/tracks/${editTrack.id}`, {
      title:        editTitle.value    || null,
      artist:       editArtist.value   || null,
      album:        editAlbum.value    || null,
      year:         editYear.value     || null,
      track_number: editTrackNum.value || null,
      genre:        editGenre.value    || null,
    });
    showToast('Metadata saved');
    closeEditModal();
    if (state.view === 'library') await loadLibrary(searchInput.value.trim());
    else await loadPlaylist(state.view);
  } catch (e) {
    showToast(`Save failed: ${e.message}`);
  } finally {
    editSave.disabled = false;
  }
}

// Modal event wiring
editClose.addEventListener('click', closeEditModal);
editCancel.addEventListener('click', closeEditModal);
editOverlay.addEventListener('click', e => { if (e.target === editOverlay) closeEditModal(); });
editSave.addEventListener('click', saveEdit);
editLookupBtn.addEventListener('click', doLookup);
editLookupQ.addEventListener('keydown', e => { if (e.key === 'Enter') doLookup(); });

// Artwork upload wiring
editArtUploadBtn.addEventListener('click', async () => {
  if (!editTrack) return;
  const file = editArtFile.files?.[0];
  if (!file) { showToast('Select an image file first'); return; }
  editArtUploadBtn.disabled = true;
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch(`/api/tracks/${editTrack.id}/set-art`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
    showToast('Artwork updated');
    editArtFile.value = '';
    if (state.view === 'library') await loadLibrary(searchInput.value.trim());
    else await loadPlaylist(state.view);
    // Refresh now-playing art if this is the current track
    if (state.currentTrack?.id === editTrack.id) {
      state.currentTrack.has_artwork = true;
      updateNowPlaying();
    }
  } catch (err) {
    showToast(`Art upload failed: ${err.message}`);
  } finally {
    editArtUploadBtn.disabled = false;
  }
});

async function fetchArtForTrack(track) {
  try {
    await api('POST', `/tracks/${track.id}/fetch-art`);
    showToast(`Artwork fetched for "${track.title || track.id}"`);
    if (state.view === 'library') await loadLibrary(searchInput.value.trim());
    else await loadPlaylist(state.view);
  } catch (e) {
    showToast(`Fetch art failed: ${e.message}`);
  }
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
      <td class="col-plays">${track.play_count ?? 0}</td>
      <td class="col-actions">
        <button class="btn-row btn-add"  title="Add to playlist">+</button>
        <button class="btn-row btn-edit" title="Edit metadata">✏</button>
        <button class="btn-row btn-art"  title="Fetch artwork">🎨</button>
        <button class="btn-row btn-copy" title="Copy to device">💾</button>
        ${showRemove
          ? `<button class="btn-row btn-rm"  title="Remove from playlist">✕</button>`
          : `<button class="btn-row btn-del" title="Delete from library">🗑</button>`}
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

    // Edit metadata button
    tr.querySelector('.btn-edit').addEventListener('click', e => {
      e.stopPropagation();
      openEditModal(track);
    });

    // Fetch artwork button
    tr.querySelector('.btn-art').addEventListener('click', e => {
      e.stopPropagation();
      fetchArtForTrack(track);
    });

    // Copy to device button
    tr.querySelector('.btn-copy').addEventListener('click', e => {
      e.stopPropagation();
      copyTrackToDevice(track);
    });

    // Remove from playlist button
    if (showRemove) {
      tr.querySelector('.btn-rm').addEventListener('click', async e => {
        e.stopPropagation();
        await api('DELETE', `/playlists/${playlistId}/tracks/${track.id}`);
        showToast('Removed from playlist');
        await loadPlaylist(playlistId);
      });
    } else {
      // Delete from library button (library view only)
      tr.querySelector('.btn-del').addEventListener('click', async e => {
        e.stopPropagation();
        if (!confirm(`Remove "${track.title || track.path}" from library?`)) return;
        try {
          await api('DELETE', `/tracks/${track.id}`);
          showToast('Track removed from library');
          await loadLibrary(searchInput.value.trim());
        } catch (err) {
          showToast(`Delete failed: ${err.message}`);
        }
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

  // Record play (fire-and-forget)
  api('POST', `/tracks/${track.id}/played`).catch(() => {});
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
  if (state.repeat) {
    // Replay the current track from the start
    audio.currentTime = 0;
    audio.play().catch(() => {});
    return;
  }
  if (state.shuffle) {
    state.queueIndex = Math.floor(Math.random() * state.queue.length);
  } else {
    state.queueIndex = (state.queueIndex + 1) % state.queue.length;
  }
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

// ── Device refresh ────────────────────────────────────────────────

btnRefreshDevices.addEventListener('click', loadDevices);

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

// ── Fetch Art (bulk) ─────────────────────────────────────────────

btnFetchArtAll.addEventListener('click', async () => {
  btnFetchArtAll.disabled = true;
  scanStatus.textContent = 'Fetching artwork…';
  try {
    const res = await api('POST', '/library/fetch-art');
    const { fetched, skipped, errors } = res;
    scanStatus.textContent =
      `✓ Art: ${fetched} fetched, ${skipped} skipped` +
      (errors.length ? `, ${errors.length} error(s)` : '');
    if (fetched > 0 && state.view === 'library') {
      await loadLibrary(searchInput.value.trim());
    }
  } catch (e) {
    scanStatus.textContent = `Error: ${e.message}`;
  } finally {
    btnFetchArtAll.disabled = false;
  }
});

// ── Shuffle / Repeat ──────────────────────────────────────────────

btnShuffle.addEventListener('click', () => {
  state.shuffle = !state.shuffle;
  btnShuffle.classList.toggle('active', state.shuffle);
  showToast(state.shuffle ? 'Shuffle on' : 'Shuffle off');
});

btnRepeat.addEventListener('click', () => {
  state.repeat = !state.repeat;
  btnRepeat.classList.toggle('active', state.repeat);
  showToast(state.repeat ? 'Repeat on' : 'Repeat off');
});

// ── Column sort ───────────────────────────────────────────────────

document.getElementById('track-table').addEventListener('click', e => {
  const th = e.target.closest('th[data-sort]');
  if (!th) return;
  const key = th.dataset.sort;
  if (state.sortKey === key) {
    state.sortDir *= -1;
  } else {
    state.sortKey = key;
    state.sortDir = 1;
  }
  // Update sort indicators
  document.querySelectorAll('th[data-sort]').forEach(el => {
    el.classList.remove('sort-asc', 'sort-desc');
    if (el.dataset.sort === state.sortKey) {
      el.classList.add(state.sortDir === 1 ? 'sort-asc' : 'sort-desc');
    }
  });
  // Sort the current track list and re-render
  const sorted = [...state.tracks].sort((a, b) => {
    const av = a[key] ?? '';
    const bv = b[key] ?? '';
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * state.sortDir;
    return String(av).localeCompare(String(bv), undefined, { numeric: true }) * state.sortDir;
  });
  const showRemove = typeof state.view === 'number';
  renderTracks(sorted, { showRemove, playlistId: showRemove ? state.view : null });
});

// ── Keyboard shortcuts ────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !editOverlay.classList.contains('hidden')) {
    closeEditModal();
    return;
  }
  // Space = play/pause (unless typing in an input)
  if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    if (state.currentTrack) state.isPlaying ? audio.pause() : audio.play();
  }
  if (e.code === 'ArrowRight' && e.altKey) { e.preventDefault(); playNext(); }
  if (e.code === 'ArrowLeft'  && e.altKey) { e.preventDefault(); playPrev(); }
});

// ── Drag-and-drop file upload ─────────────────────────────────────

const dropOverlay = document.getElementById('drop-overlay');
const AUDIO_EXTS  = /\.(mp3|flac|m4a|aac|wav)$/i;

document.addEventListener('dragover', e => {
  e.preventDefault();
  dropOverlay.classList.add('active');
});

document.addEventListener('dragleave', e => {
  // Only hide when the cursor truly leaves the window
  if (!e.relatedTarget) dropOverlay.classList.remove('active');
});

document.addEventListener('drop', async e => {
  e.preventDefault();
  dropOverlay.classList.remove('active');

  const files = [...(e.dataTransfer?.files ?? [])].filter(f => AUDIO_EXTS.test(f.name));
  if (!files.length) { showToast('No supported audio files dropped'); return; }

  showToast(`Uploading ${files.length} file${files.length !== 1 ? 's' : ''}…`);

  const form = new FormData();
  files.forEach(f => form.append('files', f));

  try {
    const res = await fetch('/api/library/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
    const data = await res.json();
    showToast(`Added ${data.saved} file${data.saved !== 1 ? 's' : ''} to library`);
    if (state.view === 'library') await loadLibrary(searchInput.value.trim());
  } catch (err) {
    showToast(`Upload failed: ${err.message}`);
  }
});

// ── Init ──────────────────────────────────────────────────────────

(async function init() {
  audio.volume = volBar.value / 100;
  await Promise.all([loadPlaylists(), loadLibrary(), loadDevices()]);
})();
