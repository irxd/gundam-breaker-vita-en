// Page code for the web patcher: folder picking, status, progress and saving. Logic lives in core.js.
import { identify, candidates, patchFile, PatchError } from './core.js';
import { makeZip, crc32 } from './zip.js';
import { titleFileKind, renameSfo, renameAppDb, loadSqlJs, TitleError, EN } from './title.js';

const $ = (s) => document.querySelector(s);
// found: patch name -> { file, entry }; bad: source path -> message (right path, wrong content)
const state = { manifest: null, found: new Map(), bad: new Map(), checking: 0, hashing: null, busy: false, done: false };
const canPickFolder = 'showDirectoryPicker' in window;
const mb = (n) => (n < 10485760 ? (n / 1048576).toFixed(1) : Math.round(n / 1048576)) + ' MB';
const gb = (n) => (n / 1073741824).toFixed(1) + ' GB';
const isEboot = (e) => e.source.origin === 'eboot';
const dataEntries = () => state.manifest.files.filter((e) => !isEboot(e));
const ebootFound = () => [...state.found.values()].find((j) => isEboot(j.entry));
// the eboot (FAGDec's eboot.bin.elf, either game version) is optional: without it only the text built into the
// game program stays Japanese
// the movies are optional too (finalizedPSP2/GP/movie): without them only their subtitles stay Japanese
const missing = () => dataEntries().filter((e) => !e.optional && !state.found.has(e.patch));
const missingMovies = () => dataEntries().filter((e) => e.optional && !state.found.has(e.patch));

async function init() {
  try {
    const r = await fetch('patcher/patches/manifest.json', { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    state.manifest = await r.json();
    $('#patch-version').textContent = 'v' + state.manifest.version;
  } catch {
    showError('Could not load the patch files. Reload the page to try again.');
    return;
  }
  $('[data-slot="app"]').addEventListener('click', () => $('#dir-app').click());
  $('[data-slot="eboot"]').addEventListener('click', () => $('#file-eboot').click());
  for (const id of ['#dir-app', '#file-eboot'])
    $(id).addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
  $('#title-pick').addEventListener('click', () => $('#title-file').click());
  $('#title-file').addEventListener('change', (e) => { if (e.target.files[0]) renameTitle(e.target.files[0]); e.target.value = ''; });
  const drop = $('#drop');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', (e) => { if (!drop.contains(e.relatedTarget)) drop.classList.remove('over'); });
  drop.addEventListener('drop', async (e) => {
    e.preventDefault();
    drop.classList.remove('over');
    addFiles(await droppedFiles(e.dataTransfer));
  });
  $('#patch').addEventListener('click', run);
  $('#zip').addEventListener('change', render);
  if (!canPickFolder) {                          // Firefox / Safari: zip only
    $('#zip').checked = true;
    $('#zip').disabled = true;
  }
  render();
}

// files of dropped folders, with their path inside the dropped folder (relPath)
async function droppedFiles(dt) {
  const roots = [...dt.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!roots.length) return [...dt.files];
  const out = [];
  const walk = async (en) => {
    if (en.isFile) {
      const f = await new Promise((ok, no) => en.file(ok, no));
      f.relPath = en.fullPath.replace(/^\//, '');
      out.push(f);
    } else if (en.isDirectory) {
      const reader = en.createReader();
      for (;;) {
        const batch = await new Promise((ok, no) => reader.readEntries(ok, no));
        if (!batch.length) break;
        for (const c of batch) await walk(c);
      }
    }
  };
  for (const en of roots) await walk(en);
  return out;
}

async function addFiles(list) {
  if (state.busy) return;
  hideError();
  state.done = false;
  if (/\.(db|sfo)$/i.test(list[0]?.name ?? '') && list.length === 1 && !list[0].webkitRelativePath) {
    renameTitle(list[0]);                         // a dropped app.db / param.sfo
    return;
  }
  // only files with a path and size we need are hashed, so picking the whole game folder stays quick
  const todo = [...list].filter((f) => candidates(f, state.manifest).length);
  if (!todo.length) {
    const elf = [...list].find((f) => /\.elf$/i.test(f.name));
    showError(elf ? `${elf.name} is not FAGDec's decrypted eboot of game version 1.00 or 1.02.`
      : 'No files of this patch in that folder. Choose the decrypted PCSG00126 game folder (with masterPSP2 and finalizedPSP2).');
    return;
  }
  state.checking += todo.length;
  render();
  for (const file of todo) {
    state.hashing = { name: file.name, done: 0, size: file.size };
    render();
    const id = await identify(file, state.manifest, (n) => { state.hashing.done = n; renderStatus(); });
    state.hashing = null;
    state.checking--;
    if (id?.ok) {
      if (isEboot(id.entry))                    // one eboot: the last one chosen wins
        for (const [k, j] of state.found) if (isEboot(j.entry)) state.found.delete(k);
      state.found.set(id.entry.patch, { file, entry: id.entry });
      state.bad.delete(id.entry.source.path);
    } else if (id && !state.found.has(id.entry.patch)) {
      state.bad.set(id.entry.source.path, id.message);
    }
    render();
  }
}

function render() {
  const app = $('[data-slot="app"]'), nApp = dataEntries().filter((e) => state.found.has(e.patch)).length;
  const total = dataEntries().length;
  app.classList.toggle('ok', !missing().length);
  app.disabled = state.busy;
  app.querySelector('small').textContent = nApp ? `${nApp} of ${total} files found` : app.dataset.hint;
  app.querySelector('.meta').textContent = !missing().length ? 'Done' : 'Choose folder';
  const eb = $('[data-slot="eboot"]'), ej = ebootFound();
  eb.hidden = !state.manifest.files.some(isEboot);
  eb.classList.toggle('ok', !!ej);
  eb.disabled = state.busy;
  eb.querySelector('small').textContent = ej ? `eboot.bin.elf of game version ${ej.entry.source.gameVersion} found`
    : eb.dataset.hint;
  eb.querySelector('.meta').textContent = ej ? 'Done' : 'Choose file';

  const zip = $('#zip').checked;
  const outSize = dataEntries().reduce((n, e) => n + e.target.size, 0) + (ej ? ej.entry.target.size : 0);
  $('#zip-note').textContent = !canPickFolder ? `Saving to a folder needs Chrome or Edge (zip: ~${gb(outSize)})`
    : !zip ? 'Off: save straight into a folder you pick (recommended)'
    : `On: one ~${gb(outSize)} zip; needs that much free memory or disk for the browser`;
  $('#zip').disabled = state.busy || !canPickFolder;
  $('#unzip-hint').hidden = !zip;
  const miss = missing();
  const showMissing = state.found.size > 0 && miss.length > 0 && !state.checking;
  $('#missing').hidden = !showMissing && !state.bad.size;
  const lines = [...state.bad].slice(0, 4).map(([p, m]) => `${p}: ${m}`);
  if (showMissing) lines.push(`${miss.length} file${miss.length > 1 ? 's' : ''} still missing, e.g. ${miss[0].source.path}`);
  $('#missing-list').textContent = lines.join('\n');
  $('#patch').disabled = state.busy || state.checking > 0 || miss.length > 0;
  renderStatus();
}

function renderStatus() {
  if (state.busy || state.done) return;
  const miss = missing();
  if (state.checking) {
    const h = state.hashing;
    setStatus('Checking files…', h ? `${h.name}: ${mb(h.done)} of ${mb(h.size)}` : `${state.checking} to go`);
    setBar(h && h.size ? h.done / h.size : null);
    return;
  }
  setBar(null);
  if (!state.found.size) setStatus('Choose your game folder', 'Decrypted ux0:app/PCSG00126');
  else if (miss.length) setStatus(`${state.found.size} file${state.found.size > 1 ? 's' : ''} found`, 'Some game files are still missing');
  else if (missingMovies().length)
    setStatus('Ready to patch', `${missingMovies().length} movies not found: their subtitles stay Japanese ` +
      '(add the finalizedPSP2 folder to include them)');
  else setStatus('Ready to patch', $('#zip').checked ? 'Creates a zip with the rePatch folder' : 'You\'ll pick where to save it');
}

function setStatus(title, sub) { $('#status').textContent = title; $('#status-sub').textContent = sub; }
function setBar(f) { $('#bar').hidden = f == null; $('#bar i').style.width = `${Math.round((f ?? 0) * 100)}%`; }

async function run() {
  hideError();
  const mode = $('#zip').checked ? 'zip' : 'folder';
  const jobs = [...state.found.values()];
  const total = jobs.reduce((n, j) => n + j.entry.target.size, 0);
  let doneBefore = 0;
  state.busy = true; state.done = false;
  $('#done').hidden = true;
  render();
  try {
    let root = null;
    if (mode === 'folder') {
      setStatus('Pick a folder', 'The rePatch folder is created inside it');
      root = await window.showDirectoryPicker({ id: 'gb-repatch', mode: 'readwrite' });
    }
    setBar(0);
    const zipEntries = [];
    for (const job of jobs) {
      const { entry } = job;
      const patch = new Uint8Array(await (await fetch('patcher/patches/' + entry.patch)).arrayBuffer());
      const sink = mode === 'folder' ? await folderSink(root, entry.target.path) : zipSink(entry.target.path, zipEntries);
      await patchFile(job.file, entry, patch, sink, (n) => {
        const f = (doneBefore + n) / total;
        setBar(f);
        setStatus(`Patching… ${Math.floor(f * 100)}%`, entry.target.path.split('/').at(-1));
      });
      doneBefore += entry.target.size;
    }
    if (mode === 'zip') {
      setStatus('Preparing the zip…', 'Almost done');
      const blob = makeZip(zipEntries);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `rePatch-PCSG00126-english-v${state.manifest.version}.zip`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 600_000);
      setStatus('Done', 'Your browser is saving the zip');
    } else {
      setStatus('Done', `Saved into "${root.name}"`);
    }
    setBar(1);
    state.done = true;
    $('#done').hidden = false;
  } catch (err) {
    setBar(null);
    if (err?.name === 'AbortError') setStatus('Cancelled', 'Nothing was saved');
    else {
      setStatus('Patching failed', 'See the message above');
      showError(err instanceof PatchError ? err.message : `Something went wrong: ${err?.message ?? err}`);
      if (!(err instanceof PatchError)) console.error(err);
    }
    state.done = true;
  } finally {
    state.busy = false;
    render();
  }
}

async function folderSink(root, path) {
  const parts = path.split('/');
  let dir = root;
  for (const p of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(p, { create: true });
  const fh = await dir.getFileHandle(parts.at(-1), { create: true });
  const w = await fh.createWritable();
  return { write: (b) => w.write(b), close: () => w.close(), abort: () => w.abort().catch(() => {}) };
}

// Zip: every window becomes its own Blob, so Chromium can keep the ~2 GB on disk instead of in memory.
function zipSink(path, list) {
  const e = { path, parts: [], size: 0, crc: 0 };
  return {
    write: async (b) => { e.parts.push(new Blob([b])); e.crc = crc32(e.crc, b); e.size += b.length; },
    close: async () => { list.push(e); },
    abort: async () => {},
  };
}

// Optional English game name: app.db (or a param.sfo) in, the changed file saved back out.
async function renameTitle(file) {
  const note = $('#title-note'), meta = $('#title-meta');
  hideError();
  note.textContent = 'Working…';
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const kind = titleFileKind(bytes);
    if (!kind) throw new TitleError(`${file.name} is not app.db or param.sfo.`);
    const r = kind === 'sfo' ? renameSfo(bytes) : renameAppDb(await loadSqlJs(), bytes);
    if (!r.changed) {
      note.textContent = `Nothing to change: the name is already "${EN}".`;
      meta.textContent = 'Choose';
      return;
    }
    const name = kind === 'sfo' ? 'param.sfo' : 'app.db';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([r.bytes], { type: 'application/octet-stream' }));
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
    note.textContent = kind === 'sfo'
      ? 'Saved param.sfo: put it back in sce_sys/.'
      : 'Saved app.db: copy it back to ur0:shell/db/ and restart the Vita.';
    meta.textContent = 'Done';
  } catch (err) {
    note.textContent = 'Not changed';
    meta.textContent = 'Choose';
    showError(err instanceof TitleError ? err.message : `Something went wrong: ${err?.message ?? err}`);
    if (!(err instanceof TitleError)) console.error(err);
  }
}

function showError(msg) { $('#error').textContent = msg; $('#error-card').hidden = false; }
function hideError() { $('#error-card').hidden = true; }

init();
