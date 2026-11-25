// Incremental SHA-1 (FIPS 180-4), for files too big for crypto.subtle.digest (it needs the whole file as one
// ArrayBuffer; the game archive is 1.5 GB). No page code, so it runs the same in the browser and in Node.

export class Sha1 {
  constructor() {
    this.h = new Uint32Array([0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0]);
    this.w = new Uint32Array(80);
    this.buf = new Uint8Array(64);
    this.bufLen = 0;
    this.total = 0;                      // bytes so far (fits a double exactly up to 2^53)
  }

  update(data) {
    let i = 0;
    const n = data.length;
    this.total += n;
    if (this.bufLen) {
      const k = Math.min(64 - this.bufLen, n);
      this.buf.set(data.subarray(0, k), this.bufLen);
      this.bufLen += k;
      i = k;
      if (this.bufLen < 64) return this;
      this.block(this.buf, 0);
      this.bufLen = 0;
    }
    for (; i + 64 <= n; i += 64) this.block(data, i);
    if (i < n) { this.buf.set(data.subarray(i), 0); this.bufLen = n - i; }
    return this;
  }

  block(p, o) {
    const w = this.w;
    for (let t = 0; t < 16; t++, o += 4) w[t] = (p[o] << 24) | (p[o + 1] << 16) | (p[o + 2] << 8) | p[o + 3];
    for (let t = 16; t < 80; t++) { const x = w[t - 3] ^ w[t - 8] ^ w[t - 14] ^ w[t - 16]; w[t] = (x << 1) | (x >>> 31); }
    let [a, b, c, d, e] = this.h;
    for (let t = 0; t < 80; t++) {
      let f, k;
      if (t < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (t < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (t < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const tmp = (((a << 5) | (a >>> 27)) + f + e + k + w[t]) | 0;
      e = d; d = c; c = (b << 30) | (b >>> 2); b = a; a = tmp;
    }
    const h = this.h;
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e;
  }

  hex() {
    const bits = this.total * 8;
    const pad = new Uint8Array(((this.bufLen < 56 ? 56 : 120) - this.bufLen) + 8);
    pad[0] = 0x80;
    const v = new DataView(pad.buffer);
    v.setUint32(pad.length - 8, Math.floor(bits / 2 ** 32));
    v.setUint32(pad.length - 4, bits >>> 0);
    const total = this.total;
    this.update(pad);
    this.total = total;
    return [...this.h].map((x) => x.toString(16).padStart(8, '0')).join('');
  }
}

/** SHA-1 of a Blob/File, read in slices so a 1.5 GB file never sits in memory. onProgress(bytesDone). */
export async function sha1Blob(blob, onProgress, slice = 16 << 20) {
  const s = new Sha1();
  for (let pos = 0; pos < blob.size; pos += slice) {
    s.update(new Uint8Array(await blob.slice(pos, pos + slice).arrayBuffer()));
    onProgress?.(Math.min(pos + slice, blob.size));
  }
  return s.hex();
}
