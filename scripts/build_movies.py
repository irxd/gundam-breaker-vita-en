"""English for the movies with burned-in Japanese subtitles.

  python -E -P scripts/build_movies.py [--only NAME] [--preview DIR] [--ffmpeg PATH]

(-E -P instead of -I because Pillow and imageio-ffmpeg live in user site-packages; the dump is only read as data.)

Cues are in text/movies/<name>.json (English only) for finalizedPSP2/GP/movie/<name>.usm:

    {"style": "box" | "blur", "cues": [{"start": s, "end": s, "en": "line 1\\nline 2", "box": [x0, y0, x1, y1]}]}

"box" is the measured box of the Japanese text (white with a dark outline). "box" style: a dark rounded box covers
it and the English is centred on it. "blur" style (the ending's epilogue, lines over a sunset): the area is blurred
and darkened instead, with the English on top.

Only the GOPs that show a cue are re-encoded; every other picture is copied byte for byte, so the files (and the
xdelta patches) stay close to the originals:
  1. ffmpeg decodes the whole video with the cue overlays (frame numbers, -fps_mode passthrough).
  2. Each GOP (closed, I P B B ..., 1-13 pictures) that overlaps a cue is encoded on its own as MPEG-1 with
     ffmpeg's mpeg1video: same picture count, closed GOP, B-frames, and the GOP's own quantiser matrices (CRI's
     encoder uses non-default ones and changes them from GOP to GOP).
  3. ffmpeg writes one slice per thread; the originals have one slice per macroblock row, and on a real Vita CRI's
     decoder shows flickering garbage for slices that span rows (Vita3K/ffmpeg don't mind). tools/mpeg1.py's
     reslice() splits every picture into one slice per row without changing what it decodes to.
  3b. The movies use 11-bit intra DC precision (TMPGEnc "IDCPREC" user data in every sequence header, mpeg_dcprec
     11 in the USM header), which ffmpeg's MPEG-1 encoder can't write: tools/mpeg1.py re-codes every intra DC
     differential of the encoded pictures from 8 to 11 bits (exactly the same values).
  4. The quantiser is the lowest that keeps the GOP within BUDGET (150%) of the original bytes and every picture within the
     file's largest original picture (so the player's buffers still fit).
  5. The encoded GOP's sequence header, user data and GOP header are replaced by the original ones (same matrices,
     DC precision, rate fields and time code), and its pictures replace the original pictures in the USM
     (tools/usm.py rebuilds the chunk sizes and the header, stream and seek tables). Audio chunks are copied.
Output: build/patched/PCSG00126/finalizedPSP2/GP/movie/<name>.usm (make_release.py takes it from there).
--preview DIR writes a before/after sheet per movie (one frame per cue).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import mpeg1  # noqa: E402
import usm  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

MOVIES = ROOT / "dump/app/PCSG00126/finalizedPSP2/GP/movie"
CUES = ROOT / "text/movies"
OUT = ROOT / "build/patched/PCSG00126/finalizedPSP2/GP/movie"
FONT = Path("C:/Windows/Fonts/arialbd.ttf")
SIZE, MIN_SIZE = 21, 14             # English font size (the Japanese glyphs are ~20 px)
BUDGET = 1.5                        # a re-encoded GOP may take up to this times the original bytes
DC_SHIFT = 3                        # 8-bit DC from ffmpeg -> the movies' 11-bit DC (see tools/mpeg1.py)
PAD = 4                             # frames added before and after each cue (the Japanese fades in and out)
ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7,
          14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46,
          53, 60, 61, 54, 47, 55, 62, 63]


def find_ffmpeg(arg):
    if arg:
        return arg
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg")


# --- MPEG-1 elementary stream ---------------------------------------------------------------------------------

class Bits:
    def __init__(self, b):
        self.b, self.p = b, 0

    def read(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.p >> 3] >> (7 - (self.p & 7))) & 1)
            self.p += 1
        return v


def sequence_header(es):
    """(width, height, frame rate code, intra matrix, inter matrix) of the first sequence header; matrices in
    bitstream (zigzag) order, None = default."""
    i = es.find(b"\0\0\1\xb3")
    b = Bits(es[i + 4:i + 200])
    w, h, _, fr = b.read(12), b.read(12), b.read(4), b.read(4)
    b.read(18 + 1 + 10 + 1)
    intra = [b.read(8) for _ in range(64)] if b.read(1) else None
    inter = [b.read(8) for _ in range(64)] if b.read(1) else None
    return w, h, fr, intra, inter


def picture_type(pic):
    """1 = I, 2 = P, 3 = B, from a payload that starts at (or contains) a picture start code."""
    q = pic.find(b"\0\0\1\0")
    return (pic[q + 5] >> 3) & 7


def split_pictures(es):
    """[(prefix, [picture, ...])]: the bytes before the first picture (sequence header, user data, GOP header) and
    each picture from its start code up to the next picture (or the end; a sequence end code is dropped)."""
    if es.endswith(b"\0\0\1\xb7"):
        es = es[:-4]
    starts = []
    p = es.find(b"\0\0\1\0")
    while p >= 0:
        starts.append(p)
        p = es.find(b"\0\0\1\0", p + 4)
    pics = [es[a:b] for a, b in zip(starts, starts[1:] + [len(es)])]
    return es[:starts[0]], pics


def natural(zigzag_matrix):
    m = [0] * 64
    for i, v in enumerate(zigzag_matrix):
        m[ZIGZAG[i]] = v
    return ",".join(map(str, m))


def encode_gop(ff, frames, size, rate, matrices, q):
    w, h = size
    args = [ff, "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-r", rate,
            "-i", "-", "-c:v", "mpeg1video", "-q:v", str(q), "-g", str(len(frames)), "-bf", "2", "-b_strategy", "0",
            "-sc_threshold", "1000000000", "-flags", "+cgop", "-mbd", "rd", "-trellis", "1", "-cmp", "2", "-subcmp", "2"]
    intra, inter = matrices
    if intra:
        args += ["-intra_matrix", natural(intra)]
    if inter:
        args += ["-inter_matrix", natural(inter)]
    args += ["-f", "mpeg1video", "-"]
    return subprocess.run(args, input=b"".join(frames), capture_output=True, check=True).stdout


# --- cue images ----------------------------------------------------------------------------------------------

def text_image(text, maxw):
    lines = text.split("\n")
    for size in range(SIZE, MIN_SIZE - 1, -1):
        f = ImageFont.truetype(str(FONT), size)
        if max(f.getlength(l) for l in lines) + 6 <= maxw:
            break
    asc, desc = f.getmetrics()
    lh = asc + desc
    w = int(max(f.getlength(l) for l in lines)) + 6
    img = Image.new("RGBA", (w, lh * len(lines) + 4))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text(((w - f.getlength(l)) / 2, 2 + i * lh), l, font=f, fill=(255, 255, 255, 255), stroke_width=2,
               stroke_fill=(0, 0, 0, 255))
    return img


def cue_layers(style, cue, width, height):
    """[(kind, image or None, x, y, w, h)]: kind 'img' = overlay an image, 'blur' = blur the area."""
    x0, y0, x1, y1 = cue["box"]
    t = text_image(cue["en"], width - 40)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w = max(x1 - x0 + 16, t.width + 20)
    h = max(y1 - y0 + 10, t.height + 8)
    x = int(min(max(4, cx - w / 2), width - 4 - w))
    y = int(min(max(4, cy - h / 2), height - 4 - h))
    w, h = int(w), int(h)
    tx, ty = x + (w - t.width) // 2, y + (h - t.height) // 2
    if style == "blur":
        return [("blur", None, x, y, w, h), ("img", t, tx, ty, t.width, t.height)]
    box = Image.new("RGBA", (w, h))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, w - 1, h - 1), radius=8, fill=(12, 12, 18, 255))
    box.alpha_composite(t, (tx - x, ty - y))
    return [("img", box, x, y, w, h)]


# --- build ---------------------------------------------------------------------------------------------------

def probe(ff, path):
    info = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    video = info.split(" Video: ")[1].split("\n")[0]
    size = next(s for s in video.split(", ") if "x" in s and s.split("x")[0].isdigit())
    w, h = int(size.split("x")[0]), int(size.split("x")[1].split(" ")[0])
    return w, h


def decode(ff, path, w, h, layers, tmp):
    """Yield the decoded frames (yuv420p bytes) with the cue layers drawn in."""
    args = [ff, "-loglevel", "error", "-i", str(path)]
    chain, last, k = [], "0:v", 0
    for i, (kind, img, x, y, lw, lh, a, b) in enumerate(layers):
        en = f"enable='between(n,{a},{b})'"
        if kind == "img":
            p = tmp / f"cue{i:03d}.png"
            img.save(p)
            args += ["-i", str(p)]
            k += 1
            chain.append(f"[{last}][{k}:v]overlay={x}:{y}:{en}[v{i}]")
        else:
            chain.append(f"[{last}]split[m{i}][c{i}];[c{i}]crop={lw}:{lh}:{x}:{y},gblur=sigma=9,"
                         f"eq=brightness=-0.13[b{i}];[m{i}][b{i}]overlay={x}:{y}:{en}[v{i}]")
        last = f"v{i}"
    script = tmp / "filter.txt"
    script.write_text(";".join(chain) + f";[{last}]format=yuv420p[out]" if chain else "[0:v]format=yuv420p[out]")
    args += ["-/filter_complex", str(script), "-map", "[out]", "-fps_mode", "passthrough", "-f", "rawvideo",
             "-pix_fmt", "yuv420p", "-"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    fs = w * h * 3 // 2
    while True:
        b = p.stdout.read(fs)
        if len(b) < fs:
            break
        yield b
    p.wait()


def cue_frames(cues, fps, total):
    """[(first frame, last frame)] for the cues sorted by start: PAD frames added on both sides, but never into a
    neighbouring cue. Cues that follow each other directly (one ends where the next starts) switch on that frame;
    with a smaller gap than 2 * PAD the gap is split in the middle. (Overlapping ranges drew both boxes and both
    lines on top of each other for ~8 frames at every change of line.)"""
    raw = [(round(c["start"] * fps), round(c["end"] * fps) - 1) for c in sorted(cues, key=lambda c: c["start"])]
    out = [[max(0, a - PAD), min(total - 1, b + PAD)] for a, b in raw]
    for i in range(len(out) - 1):
        if out[i][1] >= out[i + 1][0]:
            m = (raw[i][1] + 1 + raw[i + 1][0] + 1) // 2      # first frame of the next cue's range
            m = max(m, raw[i][1] + 1) if raw[i][1] < raw[i + 1][0] else raw[i + 1][0]
            out[i][1], out[i + 1][0] = m - 1, m
    for i, (a, b) in enumerate(out):
        if a > b:
            raise SystemExit(f"cue {i}: no frames left after removing the overlap with its neighbours")
    return [tuple(x) for x in out]


def build(ff, name, spec, out, tmp):
    src = MOVIES / f"{name}.usm"
    data = src.read_bytes()
    u = usm.Usm(data)
    tabs, _ = u.tables()
    vh = tabs[(b"@SFV", usm.HEADER)]
    total = vh.get(0, "total_frames")
    fps_n, fps_d = vh.get(0, "framerate_n"), vh.get(0, "framerate_d")
    fps = fps_n / fps_d
    rate = "30000/1001" if 29960 <= fps_n <= 29980 and fps_d == 1000 else f"{fps_n}/{fps_d}"
    w, h = probe(ff, src)
    vid = u.video()
    first = u.chunks[vid[0]].payload
    sw, sh = sequence_header(first)[:2]
    if (sw, sh) != (w, h):
        raise SystemExit(f"{name}: sequence header says {sw}x{sh}, ffmpeg {w}x{h}")
    pic_max = max(len(u.chunks[i].payload) for i in vid)

    layers, spans = [], []
    for c, (a, b) in zip(sorted(spec["cues"], key=lambda c: c["start"]), cue_frames(spec["cues"], fps, total)):
        for kind, img, x, y, lw, lh in cue_layers(spec["style"], c, w, h):
            layers.append((kind, img, x, y, lw, lh, a, b))
        spans.append((a, b))
    gops = u.gops()
    todo = [g for g in gops if any(a <= g[0] + g[1] - 1 and g[0] <= b for a, b in spans)]
    want = {}                                   # picture index -> GOP
    for g in todo:
        for n in range(g[0], g[0] + g[1]):
            want[n] = g

    pictures, frames, n = {}, {}, 0
    stats = []
    for frame in decode(ff, src, w, h, layers, tmp):
        if n in want:
            frames[n] = frame
            g = want[n]
            if n == g[0] + g[1] - 1:
                pictures.update(encode_one(ff, u, vid, g, [frames.pop(k) for k in range(g[0], g[0] + g[1])],
                                           (w, h), rate, pic_max, stats, name))
        n += 1
    if n != total:
        raise SystemExit(f"{name}: ffmpeg decoded {n} frames, the header says {total}")
    new = u.rebuild(pictures)
    dst = out / f"{name}.usm"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(new)
    old_bytes = sum(len(u.chunks[vid[k]].payload) for k in pictures)
    new_bytes = sum(len(p) for p in pictures.values())
    qs = sorted({q for q, _ in stats})
    print(f"{name}: {len(spec['cues'])} cues, {len(todo)} of {len(gops)} GOPs re-encoded ({len(pictures)} pictures, "
          f"{old_bytes:,} -> {new_bytes:,} bytes, q {qs}), {len(data):,} -> {len(new):,} bytes")
    return dst


def encode_one(ff, u, vid, gop, frames, size, rate, pic_max, stats, name):
    start, count = gop
    orig = [u.chunks[vid[k]].payload for k in range(start, start + count)]
    target = sum(len(p) for p in orig)
    prefix_orig = orig[0][:orig[0].find(b"\0\0\1\0")]
    ref = sequence_header(prefix_orig)
    if b"IDCPREC" + bytes(1) + b"0000000800000003" not in prefix_orig:
        raise SystemExit(f"{name}: GOP at {start}: no IDCPREC 3 user data; DC_SHIFT assumes 11-bit DC")
    matrices = ref[3:]                          # CRI's encoder picks the matrices per GOP
    for q in range(2, 32):
        es = encode_gop(ff, frames, size, rate, matrices, q)
        prefix, pics = split_pictures(es)
        if len(pics) != count:
            raise SystemExit(f"{name}: GOP at {start}: encoder made {len(pics)} pictures for {count} frames")
        if picture_type(pics[0]) != 1 or prefix.count(b"\0\0\1\xb8") != 1:
            raise SystemExit(f"{name}: GOP at {start}: encoder output doesn't start with one closed GOP and an I picture")
        mine = sequence_header(prefix)
        if mine[:2] != ref[:2] or mine[3:] != ref[3:]:
            raise SystemExit(f"{name}: GOP at {start}: encoder's matrices or size differ from the original")
        # one slice per macroblock row like the originals (the Vita's decoder garbles slices spanning rows)
        pics = [mpeg1.reslice(p, size[0] // 16, size[1] // 16) for p in pics]
        if DC_SHIFT:
            pics = [mpeg1.scale_dc(p, DC_SHIFT) for p in pics]
        if sum(len(p) for p in pics) <= target * BUDGET and max(len(p) for p in pics) <= pic_max:
            break
    else:
        raise SystemExit(f"{name}: GOP at {start} doesn't fit even at q 31")
    stats.append((q, start))
    pics[0] = prefix_orig + pics[0]
    return {start + i: p for i, p in enumerate(pics)}


def preview(ff, name, spec, dst, outdir):
    """A sheet with the original and the new frame in the middle of each cue."""
    src = MOVIES / f"{name}.usm"
    w, h = probe(ff, src)
    tabs, _ = usm.Usm(src.read_bytes()).tables()
    vh = tabs[(b"@SFV", usm.HEADER)]
    fps = vh.get(0, "framerate_n") / vh.get(0, "framerate_d")
    mids = [round((c["start"] + c["end"]) / 2 * fps) for c in spec["cues"]]

    def grab(path):
        sel = "+".join(f"eq(n,{f})" for f in mids + [mids[-1] + 1])
        raw = subprocess.run([ff, "-loglevel", "quiet", "-i", str(path), "-map", "0:v", "-vf", f"select='{sel}'",
                              "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        return [Image.frombytes("RGB", (w, h), raw[i:i + w * h * 3]) for i in range(0, len(raw) - w * h * 3 + 1, w * h * 3)]

    a, b = grab(src), grab(dst)
    sw, sh = w // 2, h // 2
    sheet = Image.new("RGB", (2 * sw, sh * len(mids)))
    for i, (x, y) in enumerate(zip(a, b)):
        sheet.paste(x.resize((sw, sh)), (0, i * sh))
        sheet.paste(y.resize((sw, sh)), (sw, i * sh))
    outdir.mkdir(parents=True, exist_ok=True)
    sheet.save(outdir / f"{name}.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="movie name, e.g. me01")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--ffmpeg", help="ffmpeg executable (default: $FFMPEG, imageio-ffmpeg, or ffmpeg on PATH)")
    ap.add_argument("--preview", type=Path, help="write before/after sheets here")
    a = ap.parse_args()
    ff = find_ffmpeg(a.ffmpeg)
    if not ff or not (Path(ff).is_file() or shutil.which(ff)):
        sys.exit("ffmpeg not found: pip install imageio-ffmpeg, set FFMPEG, or use --ffmpeg")
    import tempfile
    n = 0
    for f in sorted(CUES.glob("*.json")):
        if a.only and f.stem != a.only:
            continue
        spec = json.loads(f.read_text(encoding="utf-8"))
        if not spec["cues"]:
            continue
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            dst = build(ff, f.stem, spec, a.out, Path(tmp))
        if a.preview:
            preview(ff, f.stem, spec, dst, a.preview)
        n += 1
    print(f"{n} movies written to {a.out}")


if __name__ == "__main__":
    main()
