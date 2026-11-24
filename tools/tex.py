"""Gundam Breaker (Vita) `tex` payloads (decompressed entry data) <-> Pillow RGBA images.

Layout (confirmed on all 1,688 GP/ui textures and the font atlas):
  0x00  u16 width, u16 height (LE): the visible size, not always a power of two
  0x04  4 format bytes 12 41 xx yy: xx = 0x20 -> DXT5 (BC3, 16 B/block), xx = 0x00 -> DXT1 (BC1, 8 B/block);
        yy = 0x1d (low nibble d = DXT, high nibble 1 = one level, no mips) on every UI texture
  0x08  4 bytes that look like leftover memory (float bits, path fragments...): kept as they are
  0x0C  block data for the size padded up to powers of two in both directions (e.g. 1796x1796 -> 2048x2048,
        300x40 -> 512x64), no mips. Blocks are in Vita Morton order: y on the even bits, x on the odd bits;
        a non-square texture is a row/column of square tiles of the smaller side, one after the other.

decode(payload) -> RGBA image of width x height (the padding is cropped).
encode(payload, image) -> new payload of the same size: header bytes kept, and only the 4x4 blocks whose
  pixels changed are re-encoded (per block the better of an own BC1/BC3
  encoder (principal-axis endpoints refined by least squares) and Pillow's "bcn" encoder, which alone gave visibly
  wrong blocks on glow text), so an untouched image gives the original bytes back.

Command line (python -E -P, Pillow lives in user site-packages):
  tex.py decode IN.tex OUT.png
  tex.py encode IN.tex NEW.png OUT.tex
"""
import struct
import sys

from PIL import Image

HEADER = 0x0C


def _p2(x):
    n = 1
    while n < x:
        n *= 2
    return n


class Info:
    def __init__(self, payload):
        self.w, self.h = struct.unpack_from("<HH", payload, 0)
        f = payload[4:8]
        if f[0] != 0x12 or f[1] != 0x41 or (f[3] & 0x0F) != 0x0D or f[2] not in (0x00, 0x20):
            raise ValueError(f"unknown tex format {f.hex()}")
        self.dxt5 = f[2] == 0x20
        self.bsize = 16 if self.dxt5 else 8
        self.pw, self.ph = max(4, _p2(self.w)), max(4, _p2(self.h))
        self.size = (self.pw // 4) * (self.ph // 4) * self.bsize
        levels = f[3] >> 4
        if levels != 1:
            raise ValueError(f"mip levels {levels} not supported")
        if len(payload) - HEADER < self.size:
            raise ValueError(f"data {len(payload) - HEADER} < expected {self.size}")


def _morton(x, y):
    r = 0
    for i in range(16):
        r |= ((y >> i) & 1) << (2 * i) | ((x >> i) & 1) << (2 * i + 1)
    return r


def _block_order(bw, bh):
    """List: linear block index (row-major) -> swizzled block index."""
    m = min(bw, bh)
    order = [0] * (bw * bh)
    for by in range(bh):
        for bx in range(bw):
            if bw >= bh:
                tile, lx, ly = bx // m, bx % m, by
            else:
                tile, lx, ly = by // m, bx, by % m
            order[by * bw + bx] = tile * m * m + _morton(lx, ly)
    return order


def _blocks(payload, info):
    """Linear (row-major) list of block bytes over the padded size."""
    bw, bh, bs = info.pw // 4, info.ph // 4, info.bsize
    data = payload[HEADER:HEADER + info.size]
    return [data[s * bs:(s + 1) * bs] for s in _block_order(bw, bh)]


def _decode_blocks(blocks, info):
    return Image.frombytes("RGBA", (info.pw, info.ph), b"".join(blocks), "bcn", 3 if info.dxt5 else 1)


def decode(payload):
    info = Info(payload)
    img = _decode_blocks(_blocks(payload, info), info)
    return img.crop((0, 0, info.w, info.h))


def _565(c):
    return (min(31, (c[0] + 4) >> 3) << 11) | (min(63, (c[1] + 2) >> 2) << 5) | min(31, (c[2] + 4) >> 3)


def _rgb(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def _palette(c0, c1, four):
    a, b = _rgb(c0), _rgb(c1)
    if four:
        return [a, b, tuple((2 * x + y + 1) // 3 for x, y in zip(a, b)), tuple((x + 2 * y + 1) // 3 for x, y in zip(a, b))]
    return [a, b, tuple((x + y) // 2 for x, y in zip(a, b)), None]


def _fit(px, c0, c1, four, use):
    """Indices and squared error of the pixels (use[i] = pixel takes part) against a palette."""
    pal = _palette(c0, c1, four)
    idx, err = [], 0
    for p, u in zip(px, use):
        if not u:
            idx.append(3)
            continue
        best, bk = None, 0
        for k, q in enumerate(pal):
            if q is None:
                continue
            e = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
            if best is None or e < best:
                best, bk = e, k
        idx.append(bk)
        err += best
    return idx, err


def _color_block(px, punch):
    """BC1 colour block. punch: DXT1 with transparent pixels (3-colour mode, index 3 = transparent).

    Endpoint candidates: luminance extremes, bounding box corners and the extremes along the principal axis;
    the best one is refined by least squares a few times."""
    use = [not (punch and p[3] < 128) for p in px]
    vis = [p for p, u in zip(px, use) if u]
    if not vis:
        return b"\x00\x00\xff\xff\xff\xff\xff\xff"
    n = len(vis)
    mean = [sum(p[i] for p in vis) / n for i in range(3)]
    # principal axis by power iteration on the covariance
    cov = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) for p in vis) for j in range(3)] for i in range(3)]
    axis = [1.0, 1.0, 1.0]
    for _ in range(8):
        v = [sum(cov[i][j] * axis[j] for j in range(3)) for i in range(3)]
        m = max(abs(x) for x in v) or 1.0
        axis = [x / m for x in v]
    proj = [sum((p[i] - mean[i]) * axis[i] for i in range(3)) for p in vis]
    lum = [p[0] * 3 + p[1] * 6 + p[2] for p in vis]
    cands = [
        (vis[proj.index(max(proj))], vis[proj.index(min(proj))]),
        (vis[lum.index(max(lum))], vis[lum.index(min(lum))]),
        (tuple(max(p[i] for p in vis) for i in range(3)), tuple(min(p[i] for p in vis) for i in range(3))),
    ]
    best = None
    for hi, lo in cands:
        a, b = _565(hi), _565(lo)
        for _ in range(3):
            four = not punch
            idx, err = _fit(px, a, b, four, use)
            if best is None or err < best[0]:
                best = (err, a, b, idx, four)
            # least-squares refinement of the endpoints for these indices
            w = [1.0, 0.0, 2 / 3, 1 / 3] if four else [1.0, 0.0, 0.5, None]
            s_aa = s_bb = s_ab = 0.0
            s_ax, s_bx = [0.0] * 3, [0.0] * 3
            for p, k, u in zip(px, idx, use):
                if not u:
                    continue
                al = w[k]
                be = 1 - al
                s_aa += al * al
                s_bb += be * be
                s_ab += al * be
                for i in range(3):
                    s_ax[i] += al * p[i]
                    s_bx[i] += be * p[i]
            det = s_aa * s_bb - s_ab * s_ab
            if abs(det) < 1e-9:
                break
            hi = tuple(max(0, min(255, round((s_ax[i] * s_bb - s_bx[i] * s_ab) / det))) for i in range(3))
            lo = tuple(max(0, min(255, round((s_bx[i] * s_aa - s_ax[i] * s_ab) / det))) for i in range(3))
            a, b = _565(hi), _565(lo)
    err, a, b, idx, four = best
    # order the endpoints for the mode: c0 > c1 = 4 colours, c0 <= c1 = 3 colours + transparent
    if four and a < b or not four and a > b:
        a, b = b, a
        idx = [{0: 1, 1: 0}.get(k, k) if four or k != 3 else 3 for k in idx]
        if four:
            idx = [{2: 3, 3: 2}.get(k, k) for k in idx]
    if four and a == b:
        idx = [0] * 16
    bits = 0
    for i, k in enumerate(idx):
        bits |= k << (2 * i)
    return a.to_bytes(2, "little") + b.to_bytes(2, "little") + bits.to_bytes(4, "little")


def _alpha_block(a):
    hi, lo = max(a), min(a)
    if hi == lo:
        return bytes([hi, lo]) + b"\0" * 6
    pal = [hi, lo] + [((7 - k) * hi + k * lo + 3) // 7 for k in range(1, 7)]
    bits = 0
    for i, v in enumerate(a):
        bits |= min(range(8), key=lambda j: abs(pal[j] - v)) << (3 * i)
    return bytes([hi, lo]) + bits.to_bytes(6, "little")


def _block_error(tile, block, dxt5):
    got = Image.frombytes("RGBA", (4, 4), block, "bcn", 3 if dxt5 else 1).tobytes()
    want = tile.tobytes()
    err = 0
    for i in range(0, 64, 4):
        wa, ga = want[i + 3], got[i + 3]
        err += 3 * (wa - ga) ** 2
        for c in range(3):           # colour error weighted by alpha (invisible pixels don't matter)
            err += ((want[i + c] * wa - got[i + c] * ga) / 255) ** 2
    return err


def _encode_block(tile, dxt5):
    """Encode one 4x4 RGBA tile: the better of our encoder and Pillow's (each wins on different content)."""
    px = list(tile.getdata())
    if dxt5:
        ours = _alpha_block([p[3] for p in px]) + _color_block(px, False)
    else:
        ours = _color_block(px, any(p[3] < 128 for p in px))
    theirs = tile.tobytes("bcn", 3 if dxt5 else 1)
    return min((ours, theirs), key=lambda b: _block_error(tile, b, dxt5))


def encode(payload, image, force=False):
    """Return a new payload with image (RGBA, width x height) encoded in the original format.

    Blocks whose decoded pixels already equal the image are kept byte for byte (unless force)."""
    info = Info(payload)
    image = image.convert("RGBA")
    if image.size != (info.w, info.h):
        raise ValueError(f"image is {image.size}, texture is {(info.w, info.h)}")
    blocks = _blocks(payload, info)
    old = _decode_blocks(blocks, info)
    new = old.copy()
    new.paste(image, (0, 0))
    bw = info.pw // 4
    oldb, newb = old.tobytes(), new.tobytes()
    row = info.pw * 4
    changed = 0
    for by in range(info.ph // 4):
        for bx in range(bw):
            same = not force and all(
                oldb[(by * 4 + j) * row + bx * 16:(by * 4 + j) * row + bx * 16 + 16]
                == newb[(by * 4 + j) * row + bx * 16:(by * 4 + j) * row + bx * 16 + 16] for j in range(4))
            if same:
                continue
            tile = new.crop((bx * 4, by * 4, bx * 4 + 4, by * 4 + 4))
            blocks[by * bw + bx] = _encode_block(tile, info.dxt5)
            changed += 1
    out = bytearray(payload)
    order = _block_order(bw, info.ph // 4)
    bs = info.bsize
    for lin, s in enumerate(order):
        out[HEADER + s * bs:HEADER + (s + 1) * bs] = blocks[lin]
    encode.changed = changed
    return bytes(out)


def main():
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "decode":
        decode(open(a[1], "rb").read()).save(a[2])
    elif len(a) == 4 and a[0] == "encode":
        p = open(a[1], "rb").read()
        open(a[3], "wb").write(encode(p, Image.open(a[2])))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
