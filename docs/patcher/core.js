// Patcher logic without any page code, so it runs the same in the browser and in Node (for testing).
// The player picks the decrypted game folder (ux0:app/PCSG00126) and, optionally, FAGDec's eboot.bin.elf of
// game version 1.00 or 1.02. Every manifest entry names the original file by path, size and SHA-1, and the file it
// becomes in rePatch. There is one eboot entry per game version; both make rePatch/PCSG00126/eboot.bin.

import { applyPatch, PatchError } from './vcdiff.js';
import { sha1Blob } from './sha1.js';

export { PatchError };

/** SHA-1 of a File/Blob, read in 16 MB slices (the archive is 1.5 GB). onProgress(bytesDone). */
export const sha1 = (blob, onProgress) => sha1Blob(blob, onProgress);

/** Path of a picked file relative to its folder, with / separators. */
export function filePath(file) {
  return (file.webkitRelativePath || file.relPath || file.name).replace(/\\/g, '/');
}

const pathMatches = (file, e) => ('/' + filePath(file).toLowerCase()).endsWith('/' + e.source.path.toLowerCase());

/** Manifest entries whose original could be this file (same path tail and size). */
export function candidates(file, manifest) {
  return manifest.files.filter((e) => pathMatches(file, e) && e.source.size === file.size);
}

/**
 * Check one file. Returns { entry, ok, message } or null when the path is not one we patch.
 * ok=false: right path, but not the expected content (encrypted, already patched, other version).
 * onProgress(bytesHashed) while hashing.
 */
export async function identify(file, manifest, onProgress) {
  const byPath = manifest.files.filter((e) => pathMatches(file, e));
  if (!byPath.length) return null;
  const sized = byPath.filter((e) => e.source.size === file.size);
  const patched = byPath.filter((e) => e.target.size === file.size);
  if (!sized.length && !patched.length)
    return { entry: byPath[0], ok: false, message: wrongFile(byPath[0]) };
  const h = await sha1(file, onProgress);
  const e = sized.find((x) => x.source.sha1 === h);
  if (e) return { entry: e, ok: true };
  if (byPath.some((x) => x.target.sha1 === h))
    return { entry: byPath[0], ok: false, message: 'already patched' };
  return { entry: byPath[0], ok: false, message: wrongFile(byPath[0]) };
}

function wrongFile(e) {
  return e.source.origin === 'eboot'
    ? 'not the decrypted eboot of game version 1.00 or 1.02 (use FAGDec\'s eboot.bin.elf)'
    : 'different file (still encrypted? Use VitaShell\'s "Open decrypted")';
}

/**
 * Patch one file. `sink` gets the output: { write(Uint8Array): Promise, close(): Promise, abort(): Promise }.
 * onProgress(bytesDoneForThisFile). Throws PatchError with a readable message if the source doesn't match.
 */
export async function patchFile(file, entry, patchBytes, sink, onProgress) {
  const readSource = async (pos, len) => new Uint8Array(await file.slice(pos, pos + len).arrayBuffer());
  try {
    const size = await applyPatch(patchBytes, readSource, (w) => sink.write(w), onProgress);
    if (size !== entry.target.size) throw new PatchError('patched size is wrong');
    await sink.close();
  } catch (err) {
    await sink.abort?.();
    if (err instanceof PatchError && /checksum mismatch|too short/.test(err.message))
      throw new PatchError(`${entry.source.path} doesn't match this patch. Make sure it is the original, decrypted ` +
        'file and not already patched.');
    throw err;
  }
}
