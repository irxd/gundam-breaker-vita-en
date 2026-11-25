"""MPEG-1 video pictures: re-code the intra DC coefficients for a higher DC precision.

The game's movies (CRI Sofdec, encoded with TMPGEnc) are MPEG-1, but every sequence header carries TMPGEnc user
data "IDCPREC ... 3" and the USM header says mpeg_dcprec 11: intra DC coefficients use 11-bit precision (as in
MPEG-2 with intra_dc_precision 3: DC multiplier 1, predictor reset 1024, dct_dc_size up to 11). Plain MPEG-1
encoders (ffmpeg's mpeg1video) only write 8-bit DC, which such a decoder reads as garbage.

scale_dc(picture, shift=3) parses a picture's slices and macroblocks (ISO/IEC 11172-2 syntax and VLC tables) and
writes them back bit for bit, except that every intra block's DC differential is multiplied by 2**shift (8-bit DC
d becomes 11-bit DC 8*d: the same value after dequantisation, since the 8-bit multiplier is 8 and the 11-bit one 1).
With shift=0 the output is identical to the input, which tests the parser on every picture.
"""


def _table(spec):
    """{bit string: value} from 'code value' pairs."""
    out = {}
    for item in spec.split(";"):
        item = item.strip()
        if item:
            code, value = item.rsplit(" ", 1)
            out[code.replace(" ", "")] = value
    return out


MBA = _table("""1 1; 011 2; 010 3; 0011 4; 0010 5; 00011 6; 00010 7; 0000111 8; 0000110 9; 00001011 10; 00001010 11;
    00001001 12; 00001000 13; 00000111 14; 00000110 15; 0000010111 16; 0000010110 17; 0000010101 18; 0000010100 19;
    0000010011 20; 0000010010 21; 00000100011 22; 00000100010 23; 00000100001 24; 00000100000 25; 00000011111 26;
    00000011110 27; 00000011101 28; 00000011100 29; 00000011011 30; 00000011010 31; 00000011001 32; 00000011000 33;
    00000001111 stuff; 00000001000 esc""")

# macroblock_type -> flags: q = quant, f = motion forward, b = motion backward, p = pattern, i = intra
MBTYPE = {
    1: _table("1 i; 01 qi"),
    2: _table("1 fp; 01 p; 001 f; 00011 i; 00010 qfp; 00001 qp; 000001 qi"),
    3: _table("10 fb; 11 fbp; 010 b; 011 bp; 0010 f; 0011 fp; 00011 i; 00010 qfbp; 000011 qfp; 000010 qbp; 000001 qi"),
}

CBP = _table("""111 60; 1101 4; 1100 8; 1011 16; 1010 32; 10011 12; 10010 48; 10001 20; 10000 40; 01111 28; 01110 44;
    01101 52; 01100 56; 01011 1; 01010 61; 01001 2; 01000 62; 001111 24; 001110 36; 001101 3; 001100 63;
    0010111 5; 0010110 9; 0010101 17; 0010100 33; 0010011 6; 0010010 10; 0010001 18; 0010000 34;
    00011111 7; 00011110 11; 00011101 19; 00011100 35; 00011011 13; 00011010 49; 00011001 21; 00011000 41;
    00010111 14; 00010110 50; 00010101 22; 00010100 42; 00010011 15; 00010010 51; 00010001 23; 00010000 43;
    00001111 25; 00001110 37; 00001101 26; 00001100 38; 00001011 29; 00001010 45; 00001001 53; 00001000 57;
    00000111 30; 00000110 46; 00000101 54; 00000100 58; 000000111 31; 000000110 47; 000000101 55; 000000100 59;
    000000011 27; 000000010 39""")

# motion_code: only zero / non-zero matters here (non-zero codes end with a sign bit, included in the code)
MOTION = _table("""00000011001 -16; 00000011011 -15; 00000011101 -14; 00000011111 -13; 00000100001 -12;
    00000100011 -11; 0000010011 -10; 0000010101 -9; 0000010111 -8; 00000111 -7; 00001001 -6; 00001011 -5;
    0000111 -4; 00011 -3; 0011 -2; 011 -1; 1 0; 010 1; 0010 2; 00010 3; 0000110 4; 00001010 5; 00001000 6;
    00000110 7; 0000010110 8; 0000010100 9; 0000010010 10; 00000100010 11; 00000100000 12; 00000011110 13;
    00000011100 14; 00000011010 15; 00000011000 16""")

# dct_dc_size (luminance, chrominance), extended to size 11 as for 11-bit DC precision
DC_LUMA = _table("""100 0; 00 1; 01 2; 101 3; 110 4; 1110 5; 11110 6; 111110 7; 1111110 8; 11111110 9;
    111111110 10; 111111111 11""")
DC_CHROMA = _table("""00 0; 01 1; 10 2; 110 3; 1110 4; 11110 5; 111110 6; 1111110 7; 11111110 8; 111111110 9;
    1111111110 10; 1111111111 11""")
DC_LUMA_CODE = {int(v): k for k, v in DC_LUMA.items()}
DC_CHROMA_CODE = {int(v): k for k, v in DC_CHROMA.items()}

# DCT coefficient VLCs (table B.5c/d), without the sign bit; "eob", "esc" special. The first coefficient of a
# non-intra block uses "1" for (0,1) instead of "11" (and has no EOB).
COEF = set("""11 011 0100 0101 00101 00111 00110 000110 000111 000101 000100 0000110 0000100 0000111 0000101
    00100110 00100001 00100101 00100100 00100111 00100011 00100010 00100000
    0000001010 0000001100 0000001011 0000001111 0000001001 0000001110 0000001101 0000001000
    000000011101 000000011000 000000010011 000000010000 000000011011 000000010100 000000011100 000000010010
    000000011110 000000010101 000000010001 000000011111 000000011010 000000011001 000000010111 000000010110
    0000000011010 0000000011001 0000000011000 0000000010111 0000000010110 0000000010101 0000000010100
    0000000010011 0000000010010 0000000010001 0000000010000 0000000011111 0000000011110 0000000011101
    0000000011100 0000000011011
    00000000011111 00000000011110 00000000011101 00000000011100 00000000011011 00000000011010 00000000011001
    00000000011000 00000000010111 00000000010110 00000000010101 00000000010100 00000000010011 00000000010010
    00000000010001 00000000010000
    000000000011000 000000000010111 000000000010110 000000000010101 000000000010100 000000000010011
    000000000010010 000000000010001 000000000010000 000000000011111 000000000011110 000000000011101
    000000000011100 000000000011011 000000000011010 000000000011001
    0000000000010011 0000000000010010 0000000000010001 0000000000010000 0000000000010100 0000000000011010
    0000000000011001 0000000000011000 0000000000010111 0000000000010110 0000000000010101 0000000000011111
    0000000000011110 0000000000011101 0000000000011100 0000000000011011""".split())


class ParseError(Exception):
    pass


class Reader:
    def __init__(self, bits):
        self.s, self.p = bits, 0

    def take(self, n):
        v = self.s[self.p:self.p + n]
        if len(v) != n:
            raise ParseError("ran out of bits")
        self.p += n
        return v

    def vlc(self, table, maxlen=17):
        for n in range(1, maxlen + 1):
            v = table.get(self.s[self.p:self.p + n])
            if v is not None:
                self.p += n
                return v, self.s[self.p - n:self.p]
        raise ParseError(f"bad VLC at bit {self.p}: {self.s[self.p:self.p + 20]}")


def _coefficients(r, out, first_nonintra):
    """Copy the AC coefficients of one block up to and including the end-of-block code."""
    first = first_nonintra
    while True:
        s = r.s
        p = r.p
        if first and s[p] == "1":                         # first coefficient (0,1): "1s"
            out.append(r.take(2))
            first = False
            continue
        first = False
        if s.startswith("10", p):                         # end of block
            out.append(r.take(2))
            return
        if s.startswith("000001", p):                     # escape: run (6), level (8, or 8+8)
            code = r.take(6) + r.take(6)
            lvl = r.take(8)
            if lvl in ("00000000", "10000000"):
                lvl += r.take(8)
            out.append(code + lvl)
            continue
        for n in range(2, 17):
            if s[p:p + n] in COEF:
                out.append(r.take(n + 1))                 # code + sign
                break
        else:
            raise ParseError(f"bad DCT coefficient at bit {p}: {s[p:p + 20]}")


def _dc(r, out, chroma, shift):
    table, codes = (DC_CHROMA, DC_CHROMA_CODE) if chroma else (DC_LUMA, DC_LUMA_CODE)
    size, code = r.vlc(table, 10)
    size = int(size)
    if size == 0:
        out.append(code)
        return
    raw = int(r.take(size), 2)
    diff = raw if raw >> (size - 1) else raw - (1 << size) + 1
    if not shift:
        out.append(code + format(raw, f"0{size}b"))
        return
    diff <<= shift
    nsize = abs(diff).bit_length()
    if nsize > 11:
        raise ParseError("DC differential too large")
    nraw = diff if diff > 0 else diff + (1 << nsize) - 1
    out.append(codes[nsize] + format(nraw, f"0{nsize}b"))


def _slice(r, out, ptype, fcodes, shift):
    out.append(r.take(5))                                 # quantizer_scale
    while True:                                           # extra_bit_slice
        b = r.take(1)
        out.append(b)
        if b == "0":
            break
        out.append(r.take(8))
    while True:
        while True:                                       # macroblock_address_increment
            v, code = r.vlc(MBA, 11)
            out.append(code)
            if v not in ("stuff", "esc"):
                break
        flags, code = r.vlc(MBTYPE[ptype], 6)
        out.append(code)
        if "q" in flags:
            out.append(r.take(5))
        for d, f in (("f", fcodes[0]), ("b", fcodes[1])):
            if d in flags:
                for _ in range(2):                        # horizontal, vertical
                    mc, code = r.vlc(MOTION, 11)
                    out.append(code)
                    if f != 1 and mc != "0":
                        out.append(r.take(f - 1))
        if "i" in flags:
            cbp = 63
        elif "p" in flags:
            v, code = r.vlc(CBP, 9)
            out.append(code)
            cbp = int(v)
        else:
            cbp = 0
        for i in range(6):
            if cbp & (32 >> i):
                if "i" in flags:
                    _dc(r, out, i >= 4, shift)
                    _coefficients(r, out, False)
                else:
                    _coefficients(r, out, True)
        if ptype == 4:                                    # D picture: end_of_macroblock
            out.append(r.take(1))
        if "1" not in r.s[r.p:r.p + 23]:                  # 23 zeros (next start code) or only stuffing left
            return


def _bits(data):
    return format(int.from_bytes(data, "big"), f"0{len(data) * 8}b") if data else ""


def _bytes(bits):
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big") if bits else b""


def scale_dc(picture, shift=3):
    """Return the picture (bytes from its picture start code to the end of its last slice; anything before the
    picture start code, such as a sequence or GOP header, is copied) with intra DC differentials << shift."""
    head = picture.find(b"\0\0\1\0")
    if head < 0:
        raise ParseError("no picture start code")
    # split at start codes: picture header (+ extension/user data), then slices
    starts = []
    p = head
    while p >= 0:
        starts.append(p)
        p = picture.find(b"\0\0\1", p + 3)
    parts = [picture[a:b] for a, b in zip(starts, starts[1:] + [len(picture)])]
    hdr = Reader(_bits(parts[0][4:]))
    hdr.take(10)
    ptype = int(hdr.take(3), 2)
    hdr.take(16)
    fcodes = [1, 1]
    if ptype in (2, 3):
        hdr.take(1)
        fcodes[0] = int(hdr.take(3), 2)
    if ptype == 3:
        hdr.take(1)
        fcodes[1] = int(hdr.take(3), 2)
    out = [picture[:head]]
    for part in parts:
        code = part[3]
        if not 0x01 <= code <= 0xAF:
            out.append(part)                              # picture header, extension or user data: as is
            continue
        r = Reader(_bits(part[4:]))
        bits = []
        _slice(r, bits, ptype, fcodes, shift)
        rest = r.s[r.p:]
        if "1" in rest:
            raise ParseError(f"slice {code:#x}: {len(rest)} bits left after the last macroblock")
        new = _bytes("".join(bits))
        if not shift and new.rstrip(b"\0") != part[4:].rstrip(b"\0"):
            raise ParseError(f"slice {code:#x} does not round-trip")
        out.append(part[:4] + new)
    return b"".join(out)
