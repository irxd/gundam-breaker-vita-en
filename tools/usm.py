"""CRI USM (Sofdec 2) movies: parse, and rebuild with some video pictures replaced.

Layout (big-endian), checked on all 60 movies of the game (notes/formats.md, "Movies"):
  The file is a sequence of chunks, each aligned to 32 bytes:
    0x00 char[4] signature: CRID (file info), @SFV (video), @SFA (audio)
    0x04 u32     size of the rest of the chunk
    0x08 u8      0
    0x09 u8      payload offset from 0x08 (0x18)
    0x0A u16     padding at the end (the chunk is padded so the next one starts on a 32-byte boundary)
    0x0C u8      channel, 0x0D u8, 0x0E u8
    0x0F u8      kind: 0 = stream data, 1 = header (@UTF table), 2 = text marker ("#HEADER END", ...),
                 3 = seek table (@UTF)
    0x10 u32     time of the chunk in units of 1/frate (video: frame index * 100)
    0x14 u32     frate (fps * 100), 0x18 u32, 0x1C u32
  Video data chunks hold one MPEG-1 picture each, in coded order; the first picture of every GOP starts with the
  sequence header, user data and the GOP header. All GOPs are closed (I P B B P B B ... P B B).

@UTF tables (CRI's column store) hold the values that depend on the video stream:
  CRID  CRIUSF_DIR_STREAM  row 0 (whole file): filesize = file length, avbps = sum of the streams' avbps,
                           minbuf (a buffer size; its formula is unknown, rebuild() only adds growth to it)
                           one row per stream: filesize = sum of the stream's data payloads,
                           avbps = int(filesize * 8 / duration) (video: frames / fps, with 29.97 as 30000/1001;
                           audio: samples / rate), minbuf = largest data payload
  @SFV  VIDEO_HDRINFO      total_frames, ixsize (the largest data payload or chunk; not consistent)
  @SFV  VIDEO_SEEKINFO     one row per GOP: ofs_byte = file offset of the GOP's first chunk, ofs_frmid
rebuild() rewrites these numbers in place (the tables keep their size), so a rebuild with no replaced pictures is
byte-identical to the original.
"""
import struct

DATA, HEADER, TEXT, SEEK = 0, 1, 2, 3
VIDEO_ID = struct.unpack(">I", b"@SFV")[0]
FMT = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 0xA: ">I", 0xB: ">II"}


class Chunk:
    def __init__(self, data, pos):
        self.sig = data[pos:pos + 4]
        size, = struct.unpack_from(">I", data, pos + 4)
        self.raw = bytes(data[pos:pos + 8 + size])
        self.off = self.raw[9]
        self.pad, = struct.unpack_from(">H", self.raw, 10)
        self.kind = self.raw[15]
        self.time, = struct.unpack_from(">I", self.raw, 16)

    @property
    def payload(self):
        return self.raw[8 + self.off:len(self.raw) - self.pad]

    def with_payload(self, payload):
        """A copy of this chunk with a new payload, padded to the next 32-byte boundary."""
        c = object.__new__(Chunk)
        c.sig, c.off, c.kind, c.time = self.sig, self.off, self.kind, self.time
        c.pad = -(8 + self.off + len(payload)) % 32
        head = bytearray(self.raw[:8 + self.off])
        struct.pack_into(">I", head, 4, self.off + len(payload) + c.pad)
        struct.pack_into(">H", head, 10, c.pad)
        c.raw = bytes(head) + payload + bytes(c.pad)
        return c


class Table:
    """An @UTF table inside a chunk payload; values can be read and numbers written in place."""

    def __init__(self, buf, base):
        self.buf, self.base = buf, base            # buf: bytearray of the whole file, base: offset of "@UTF"
        assert buf[base:base + 4] == b"@UTF"
        t = base + 8
        _, rows_off, self.str_off, _, name_off, ncol, self.rowlen, self.nrows = struct.unpack_from(">HHIIIHHI", buf, t)
        self.t, self.rows_off = t, rows_off
        self.name = self._str(name_off)
        self.cols = []                              # (name, storage, type, const position or column offset)
        p, col = t + 24, 0
        for _ in range(ncol):
            fl = buf[p]
            nm, = struct.unpack_from(">I", buf, p + 1)
            p += 5
            st, ty = fl & 0xF0, fl & 0x0F
            if st == 0x30:
                self.cols.append((self._str(nm), st, ty, p))
                p += struct.calcsize(FMT[ty])
            elif st == 0x50:
                self.cols.append((self._str(nm), st, ty, col))
                col += struct.calcsize(FMT[ty])
            else:
                self.cols.append((self._str(nm), st, ty, None))

    def _str(self, o):
        o += self.t + self.str_off
        return bytes(self.buf[o:self.buf.index(0, o)]).decode("cp932")

    def _pos(self, row, name):
        for nm, st, ty, where in self.cols:
            if nm == name:
                if st == 0x50:
                    return self.t + self.rows_off + row * self.rowlen + where, ty
                if st == 0x30:
                    return where, ty
                return None, ty
        raise KeyError(name)

    def get(self, row, name):
        p, ty = self._pos(row, name)
        if p is None:
            return None
        v = struct.unpack_from(FMT[ty], self.buf, p)
        return self._str(v[0]) if ty == 0xA else v[0] if len(v) == 1 else v

    def set(self, row, name, value):
        p, ty = self._pos(row, name)
        if ty not in (0, 1, 2, 3, 4, 5, 6, 7):
            raise ValueError(f"{self.name}.{name} is not an integer column")
        struct.pack_into(FMT[ty], self.buf, p, value)

    def rows(self):
        return [{nm: self.get(r, nm) for nm, *_ in self.cols} for r in range(self.nrows)]


class Usm:
    def __init__(self, data):
        self.chunks = []
        p = 0
        while p < len(data):
            c = Chunk(data, p)
            self.chunks.append(c)
            p += len(c.raw)
        if p != len(data):
            raise ValueError("chunks don't end at the end of the file")

    def video(self):
        """Indexes (into self.chunks) of the video data chunks: one per picture, in coded order."""
        return [i for i, c in enumerate(self.chunks) if c.sig == b"@SFV" and c.kind == DATA]

    def gops(self):
        """[(first picture, number of pictures)] for each GOP; pictures counted in video() order."""
        starts = [n for n, i in enumerate(self.video()) if self.chunks[i].payload.startswith(b"\0\0\1\xb3")]
        ends = starts[1:] + [len(self.video())]
        return [(s, e - s) for s, e in zip(starts, ends)]

    def tables(self, buf=None):
        """{(signature, kind): (Table, ...)} for the @UTF tables, over buf (default: the current bytes)."""
        buf = buf if buf is not None else bytearray(b"".join(c.raw for c in self.chunks))
        out, p = {}, 0
        for c in self.chunks:
            if c.kind in (HEADER, SEEK) and c.payload[:4] == b"@UTF":
                out[(c.sig, c.kind)] = Table(buf, p + 8 + c.off)
            p += len(c.raw)
        return out, buf

    def rebuild(self, pictures=None):
        """Return the file bytes with video pictures replaced: pictures = {picture index: MPEG-1 payload}.

        Everything else is copied; the tables' sizes, rates and seek offsets are recomputed (see the module doc).
        Only the video row of the stream table changes (the audio chunks are copied). The buffer fields (minbuf of
        the video and the whole file, ixsize) grow by as much as the largest picture grew, and never shrink.
        """
        pictures = pictures or {}
        vid = self.video()
        chunks = list(self.chunks)
        for n, payload in pictures.items():
            chunks[vid[n]] = chunks[vid[n]].with_payload(payload)
        if not pictures:
            return b"".join(c.raw for c in chunks)
        new = Usm.__new__(Usm)
        new.chunks = chunks
        tabs, buf = new.tables()
        crid = tabs[(b"CRID", HEADER)]
        vh = tabs[(b"@SFV", HEADER)]
        seconds = video_seconds(vh)
        old = [self.chunks[i] for i in vid]
        data = [chunks[i] for i in vid]
        grow = max(0, max(len(c.payload) for c in data) - max(len(c.payload) for c in old))
        for r in range(crid.nrows):
            if crid.get(r, "stmid") == VIDEO_ID:
                size = sum(len(c.payload) for c in data)
                crid.set(r, "filesize", size)
                crid.set(r, "avbps", int(size * 8 / seconds))
                crid.set(r, "minbuf", crid.get(r, "minbuf") + grow)
        crid.set(0, "minbuf", crid.get(0, "minbuf") + grow)
        vh.set(0, "ixsize", vh.get(0, "ixsize") + grow)
        crid.set(0, "avbps", sum(crid.get(r, "avbps") for r in range(1, crid.nrows)))
        crid.set(0, "filesize", len(buf))
        seek = tabs.get((b"@SFV", SEEK))
        if seek:
            offsets, p = {}, 0
            for i, c in enumerate(chunks):
                offsets[i] = p
                p += len(c.raw)
            starts = [s for s, _ in self.gops()]
            if seek.nrows != len(starts):
                raise ValueError(f"seek table has {seek.nrows} rows for {len(starts)} GOPs")
            for r, s in enumerate(starts):
                if seek.get(r, "ofs_frmid") != s:
                    raise ValueError(f"seek row {r} is frame {seek.get(r, 'ofs_frmid')}, GOP starts at {s}")
                seek.set(r, "ofs_byte", offsets[vid[s]])
        return bytes(buf)


def video_seconds(vh):
    """Duration the tables use: NTSC rates (framerate_n 29969/29970) count as 30000/1001."""
    n, d = vh.get(0, "framerate_n"), vh.get(0, "framerate_d")
    if d == 1000 and 29960 <= n <= 29980:
        n, d = 30000, 1001
    return vh.get(0, "total_frames") * d / n


def check_tables(data):
    """Recompute the derived table values of an unmodified file; returns a list of mismatches (for testing)."""
    u = Usm(data)
    tabs, _ = u.tables()
    crid, vh = tabs[(b"CRID", HEADER)], tabs[(b"@SFV", HEADER)]
    seconds = video_seconds(vh)
    bad = []
    if crid.get(0, "filesize") != len(data):
        bad.append("file size")
    total = 0
    for r in range(1, crid.nrows):
        sig = struct.pack(">I", crid.get(r, "stmid"))
        size = sum(len(c.payload) for c in u.chunks if c.sig == sig and c.kind == DATA)
        bps = int(size * 8 / seconds)
        total += crid.get(r, "avbps")
        if crid.get(r, "filesize") != size:
            bad.append(f"{sig} filesize {crid.get(r, 'filesize')} != {size}")
        if sig == b"@SFV" and crid.get(r, "avbps") != bps:
            bad.append(f"{sig} avbps {crid.get(r, 'avbps')} != {bps}")
    if crid.get(0, "avbps") != total:
        bad.append("total avbps")
    if len(u.video()) != vh.get(0, "total_frames"):
        bad.append(f"{len(u.video())} pictures, total_frames {vh.get(0, 'total_frames')}")
    seek = tabs.get((b"@SFV", SEEK))
    if seek:
        offsets, p = [], 0
        for c in u.chunks:
            offsets.append(p)
            p += len(c.raw)
        vid = u.video()
        want = [(offsets[vid[s]], s) for s, _ in u.gops()]
        have = [(seek.get(r, "ofs_byte"), seek.get(r, "ofs_frmid")) for r in range(seek.nrows)]
        if want != have:
            bad.append("seek table")
    return bad
