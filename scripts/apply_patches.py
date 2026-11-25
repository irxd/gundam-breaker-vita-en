"""Apply the Gundam Breaker English patch on a PC (no other tools needed: Python 3.8+ only).

Usage:
    python apply_patches.py <decrypted game folder> [<eboot.bin.elf>] [--out <folder>]

The game folder is the decrypted copy of ux0:app/PCSG00126 (at least its masterPSP2 and finalizedPSP2 folders),
e.g. copied from VitaShell's "Open decrypted" over FTP. Each file is matched by its path, size and SHA-1, then
patched. All game data comes from the base game; the 1.02 update only changes the game program. The movies
(finalizedPSP2/GP/movie) are optional: without them only the movie subtitles stay Japanese.

Optional: FAGDec's eboot.bin.elf of the version you play (1.00: ux0:FAGDec/app/PCSG00126/eboot.bin.elf, 1.02:
ux0:FAGDec/patch/PCSG00126/eboot.bin.elf) gives the English for the text built into the game program (default
radio chat, default Gunpla name, "Not equipped", lobby). Without it, that text stays Japanese and everything else
is patched as usual.

Output: <out>/rePatch/PCSG00126/... (default out: the current folder). Copy that rePatch folder to ux0: on the
Vita (needs the rePatch plugin).

The patches and manifest.json are read from the patches/ folder next to this script (or ../patches).
The VCDIFF decoder below handles what `xdelta3 -e -S none -A` writes (same as the web patcher). The patches use a
source window as big as the 1.5 GB original, so the original is read on demand, never loaded whole.
"""
import argparse
import hashlib
import json
import sys
import zlib
from pathlib import Path

VCD_SOURCE, VCD_TARGET, VCD_ADLER32 = 1, 2, 4
NOOP, ADD, RUN, COPY = 0, 1, 2, 3


def _code_table():
    t = [(RUN, 0, 0, NOOP, 0, 0), (ADD, 0, 0, NOOP, 0, 0)]
    t += [(ADD, s, 0, NOOP, 0, 0) for s in range(1, 18)]
    for m in range(9):
        t.append((COPY, 0, m, NOOP, 0, 0))
        t += [(COPY, s, m, NOOP, 0, 0) for s in range(4, 19)]
    for m in range(6):
        t += [(ADD, a, 0, COPY, c, m) for a in range(1, 5) for c in range(4, 7)]
    for m in range(6, 9):
        t += [(ADD, a, 0, COPY, 4, m) for a in range(1, 5)]
    t += [(COPY, 4, m, ADD, 1, 0) for m in range(9)]
    assert len(t) == 256
    return t


CODE_TABLE = _code_table()


class PatchError(Exception):
    pass


class Reader:
    def __init__(self, buf, pos=0, end=None):
        self.buf, self.pos, self.end = buf, pos, len(buf) if end is None else end

    def byte(self):
        if self.pos >= self.end:
            raise PatchError('patch file is truncated or damaged')
        self.pos += 1
        return self.buf[self.pos - 1]

    def varint(self):
        v = 0
        while True:
            b = self.byte()
            v = v * 128 + (b & 0x7f)
            if not b & 0x80:
                return v

    def bytes(self, n):
        if self.pos + n > self.end:
            raise PatchError('patch file is truncated or damaged')
        self.pos += n
        return self.buf[self.pos - n:self.pos]


class Source:
    """The source segment of one window, read from the original file on demand (it can span the whole file)."""
    BLOCK = 1 << 22

    def __init__(self, f, pos, length):
        self.f, self.pos, self.len = f, pos, length
        self.cache = {}

    def __len__(self):
        return self.len

    def get(self, a, n):
        out = bytearray()
        while n > 0:
            b, o = divmod(a, self.BLOCK)
            want = min(self.BLOCK, self.len - b * self.BLOCK)
            blk = self.cache.get(b)
            if blk is None:
                if len(self.cache) >= 8:
                    self.cache.clear()
                self.f.seek(self.pos + b * self.BLOCK)
                blk = self.f.read(want)
                if len(blk) != want:
                    raise PatchError('original file is too short (wrong file?)')
                self.cache[b] = blk
            k = min(n, len(blk) - o)
            out += blk[o:o + k]
            a += k
            n -= k
        return out


def decode_window(src, tlen, data, inst, addr):
    out = bytearray(tlen)
    slen = len(src)
    near, same = [0, 0, 0, 0], [0] * 768
    nxt = 0
    t = 0

    def decode_addr(mode):
        nonlocal nxt
        here = slen + t
        if mode == 0:
            a = addr.varint()
        elif mode == 1:
            a = here - addr.varint()
        elif mode < 6:
            a = near[mode - 2] + addr.varint()
        else:
            a = same[(mode - 6) * 256 + addr.byte()]
        near[nxt] = a
        nxt = (nxt + 1) & 3
        same[a % 768] = a
        return a

    while inst.pos < inst.end:
        c = CODE_TABLE[inst.byte()]
        for typ, size, mode in ((c[0], c[1], c[2]), (c[3], c[4], c[5])):
            if typ == NOOP:
                continue
            if size == 0:
                size = inst.varint()
            if t + size > tlen:
                raise PatchError('patch writes past the end of a window (damaged patch)')
            if typ == ADD:
                out[t:t + size] = data.bytes(size)
            elif typ == RUN:
                out[t:t + size] = bytes([data.byte()]) * size
            else:
                a = decode_addr(mode)
                if a >= slen + t:
                    raise PatchError('bad copy address (damaged patch)')
                n, d = size, t
                if a < slen:
                    k = min(n, slen - a)
                    out[d:d + k] = src.get(a, k)
                    a += k
                    d += k
                    n -= k
                if n > 0:
                    s = a - slen
                    if s + n <= d:
                        out[d:d + n] = out[s:s + n]
                    else:
                        for i in range(n):
                            out[d + i] = out[s + i]
            t += size
    if t != tlen:
        raise PatchError('window size mismatch (damaged patch)')
    return out


def apply_patch(patch, src_file, out_file):
    """Apply a VCDIFF patch (bytes) to the open source file, writing the result to out_file. Returns its size."""
    r = Reader(patch)
    if bytes([r.byte(), r.byte(), r.byte()]) != b'\xd6\xc3\xc4':
        raise PatchError('not an xdelta / VCDIFF patch')
    r.byte()
    hdr = r.byte()
    if hdr & 3:
        raise PatchError('unsupported patch (secondary compression or custom code table)')
    if hdr & 4:
        r.bytes(r.varint())
    src_file.seek(0, 2)
    src_size = src_file.tell()
    total = 0
    while r.pos < r.end:
        win = r.byte()
        if win & VCD_TARGET:
            raise PatchError('target-referencing windows are unsupported')
        src = Source(src_file, 0, 0)
        if win & VCD_SOURCE:
            ln, pos = r.varint(), r.varint()
            if pos + ln > src_size:
                raise PatchError('original file is too short (wrong file?)')
            src = Source(src_file, pos, ln)
        r.varint()
        tlen = r.varint()
        if r.byte() != 0:
            raise PatchError('compressed patch sections are unsupported')
        dl, il, al = r.varint(), r.varint(), r.varint()
        want = int.from_bytes(r.bytes(4), 'big') if win & VCD_ADLER32 else None
        data = Reader(patch, r.pos, r.pos + dl)
        r.pos += dl
        inst = Reader(patch, r.pos, r.pos + il)
        r.pos += il
        addr = Reader(patch, r.pos, r.pos + al)
        r.pos += al
        out = decode_window(src, tlen, data, inst, addr)
        if want is not None and zlib.adler32(out) & 0xffffffff != want:
            raise PatchError('checksum mismatch: the original file does not match this patch')
        out_file.write(out)
        total += len(out)
    return total


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def find_source(e, inputs):
    """The input that is this entry's original file (path tail, size and SHA-1), or None."""
    rel, want, size = e['source']['path'], e['source']['sha1'], e['source']['size']
    parts = rel.split('/')
    for item in inputs:
        if item.is_file():          # a file given directly (eboot.bin.elf)
            cands = [item] if item.name.lower() == parts[-1].lower() else []
        else:                       # the game folder, or its masterPSP2 folder
            cands = [item.joinpath(*parts[k:]) for k in range(len(parts))]
        for c in cands:
            if c.is_file() and c.stat().st_size == size and sha1(c) == want:
                return c
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('inputs', nargs='+', type=Path,
                    help='decrypted game folder (ux0:app/PCSG00126), and optionally eboot.bin.elf (FAGDec)')
    ap.add_argument('--out', type=Path, default=Path('.'))
    ap.add_argument('--patches', type=Path, help='folder with manifest.json (default: patches/ next to this script)')
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    pdir = a.patches or next((p for p in (here / 'patches', here.parent / 'patches') if (p / 'manifest.json').exists()),
                             None)
    if not pdir:
        sys.exit('patches/manifest.json not found next to this script; use --patches')
    man = json.loads((pdir / 'manifest.json').read_text(encoding='utf-8'))
    data = [e for e in man['files'] if e['source']['origin'] != 'eboot']
    eboots = [e for e in man['files'] if e['source']['origin'] == 'eboot']

    print('checking files ...', flush=True)
    jobs, bad = [], 0
    skipped_movies = 0
    for e in data:
        src = find_source(e, a.inputs)
        if not src and e.get('optional'):
            skipped_movies += 1             # a movie: copy finalizedPSP2 too to get its English subtitles
            continue
        if not src:
            print(f'MISSING {e["source"]["path"]}: need the decrypted original from the game folder '
                  f'({e["source"]["size"]:,} bytes, SHA-1 {e["source"]["sha1"]})')
            bad += 1
        jobs.append((e, src))
    if skipped_movies:
        print(f'{skipped_movies} movie(s) not found (finalizedPSP2/GP/movie): skipped, their subtitles stay Japanese '
              '(optional; copy the finalizedPSP2 folder too to patch them)')
    # one eboot patch per game version; they all make rePatch/PCSG00126/eboot.bin, so use the one that matches
    eboot = next(((e, s) for e in eboots for s in [find_source(e, a.inputs)] if s), None)
    if eboot:
        jobs.append(eboot)
    elif any(p.is_file() for p in a.inputs):
        versions = ' or '.join(e['source']['gameVersion'] for e in eboots)
        print(f'eboot.bin.elf does not match: give the eboot.bin.elf FAGDec made from game version {versions} '
              '(not the encrypted eboot.bin, not an already patched file)')
        bad += 1
    else:
        print('no eboot.bin.elf given: the game program is skipped (optional; without it the default radio chat, '
              'Gunpla name, "Not equipped" and lobby text stay Japanese)')
    if bad:
        sys.exit(f'{bad} file(s) missing or not matching; nothing was written')

    for i, (e, src) in enumerate(jobs, 1):
        dst = a.out / e['target']['path']
        dst.parent.mkdir(parents=True, exist_ok=True)
        what = e['source']['path'] + (f' ({e["source"]["gameVersion"]})' if 'gameVersion' in e['source'] else '')
        print(f'[{i}/{len(jobs)}] patching {what} ...', flush=True)
        try:
            with open(src, 'rb') as sf, open(dst, 'wb') as of:
                apply_patch((pdir / e['patch']).read_bytes(), sf, of)
            if sha1(dst) != e['target']['sha1']:
                raise PatchError('patched file has the wrong checksum')
        except PatchError as err:
            print(f'[{i}/{len(jobs)}] FAILED {what}: {err}')
            dst.unlink(missing_ok=True)
            sys.exit(1)
        print(f'[{i}/{len(jobs)}] ok {e["target"]["path"]}')
    print(f'done: copy {a.out / "rePatch"} to ux0: on your Vita')


if __name__ == '__main__':
    main()
