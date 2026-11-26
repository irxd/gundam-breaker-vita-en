// Run the web patcher's code (docs/patcher/core.js, vcdiff.js, sha1.js, title.js) under Node against the dump:
// identify every original, apply every patch and check the SHA-1 of the result against the manifest.
//
//   node scripts/test_web_patcher.mjs [patches folder]      (default docs/patcher/patches)
//
// Needs Node 20+ (fs.openAsBlob gives a lazily read Blob, like a picked File in the browser). Reads:
//   dump/app/PCSG00126/<path>              originals of the data files
//   dump/eboot/{app,patch}/eboot.bin.elf   FAGDec eboots of 1.00 and 1.02
//   dump/app/PCSG00126/sce_sys/param.sfo   for the title step
// Nothing is written: the patched output is only hashed.
import { openAsBlob } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const P = (rel) => new URL('file:///' + join(ROOT, 'docs/patcher', rel).replace(/\\/g, '/')).href;
const { identify, candidates, patchFile } = await import(P('core.js'));
const { Sha1 } = await import(P('sha1.js'));
const { renameSfo, titleFileKind } = await import(P('title.js'));

const pdir = resolve(process.argv[2] ?? join(ROOT, 'docs/patcher/patches'));
const manifest = JSON.parse(await readFile(join(pdir, 'manifest.json'), 'utf8'));
let failed = 0;
const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) failed++; };

// 1. the incremental SHA-1 matches Node's
for (const n of [0, 1, 55, 56, 63, 64, 65, 1000, 200003]) {
  const buf = new Uint8Array(n).map((_, i) => (i * 7 + 3) & 255);
  const s = new Sha1();
  for (let i = 0; i < n; i += 37) s.update(buf.subarray(i, i + 37));   // odd slices on purpose
  check(s.hex() === createHash('sha1').update(buf).digest('hex'), `sha1 of ${n} bytes`);
}

// 2. every patch, on its original from the dump
async function original(e) {
  if (e.source.origin !== 'eboot') return join(ROOT, 'dump/app/PCSG00126', e.source.path);
  return join(ROOT, 'dump/eboot', e.source.gameVersion === '1.00' ? 'app' : 'patch', 'eboot.bin.elf');
}

for (const e of manifest.files) {
  const path = await original(e);
  const blob = await openAsBlob(path);
  const file = new File([blob], e.source.path.split('/').at(-1));   // File over the lazy Blob: nothing is read yet
  file.relPath = 'PCSG00126/' + e.source.path;
  check(candidates(file, manifest).includes(e), `${e.patch}: candidate by path and size`);
  const t0 = Date.now();
  const id = await identify(file, manifest);
  check(id?.ok && id.entry === e, `${e.patch}: identified (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  const h = new Sha1();
  let size = 0;
  const sink = { write: async (b) => { h.update(b); size += b.length; }, close: async () => {}, abort: async () => {} };
  const patch = new Uint8Array(await readFile(join(pdir, e.patch)));
  const t1 = Date.now();
  await patchFile(file, e, patch, sink);
  const got = h.hex();
  check(size === e.target.size && got === e.target.sha1,
    `${e.patch}: patched ${size.toLocaleString()} bytes, SHA-1 ${got} (${((Date.now() - t1) / 1000).toFixed(1)} s)`);
}

// 3. a wrong file is rejected without patching
{
  const e = manifest.files.find((x) => x.source.origin === 'eboot');
  if (e) {
    const fake = new File([new Uint8Array(e.source.size)], 'eboot.bin.elf');
    const id = await identify(fake, manifest);
    check(id && !id.ok, `zero-filled eboot.bin.elf rejected: ${id?.message}`);
  }
}

// 4. title step on the game's param.sfo
{
  const sfo = new Uint8Array(await readFile(join(ROOT, 'dump/app/PCSG00126/sce_sys/param.sfo')));
  check(titleFileKind(sfo) === 'sfo', 'param.sfo recognised');
  const r = renameSfo(sfo);
  const text = new TextDecoder().decode(r.bytes);
  check(r.changed && text.includes('GUNDAM BREAKER') && text.includes('GUNDAM\nBREAKER'), 'param.sfo renamed');
}

console.log(failed ? `\n${failed} check(s) FAILED` : '\nall checks passed');
process.exit(failed ? 1 : 0);
