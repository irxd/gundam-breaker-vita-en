"""Build fake-signed eboot.bin and sce_module/*.suprx (fself) from FAGDec-decrypted ELFs.

  python -I scripts/make_eboot.py [app|patch] [ELF]

Defaults: version "patch" (1.02). Inputs from dump/eboot/<version>/:
  eboot.bin.elf (+ .sha256), sce_module/*.suprx.elf (+ .sha256), self_auth.bin
The game's modules carry the same authid as the eboot (checked against the original SELF headers), so
self_auth.bin is used for all of them.
Output: build/eboot/<version>/eboot.bin and build/eboot/<version>/sce_module/*.suprx
Give a different eboot ELF (e.g. a patched one) as the second argument; modules are then still built from the dump.

The modules are only needed for Vita3K. On a real Vita, rePatch leaves the original modules in place.
"""
import glob
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fself  # noqa: E402


def build(elf_path, dst, authid, check_sha=True):
    elf = open(elf_path, "rb").read()
    sha_path = elf_path + ".sha256"
    if check_sha and os.path.exists(sha_path):
        if hashlib.sha256(elf).digest() != open(sha_path, "rb").read():
            sys.exit(f"{elf_path} does not match {sha_path}")
    out = fself.make_fself(elf, authid=authid)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(out)
    print(f"{len(elf):>9} -> {len(out):>9} bytes: {os.path.relpath(dst, ROOT)}")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if version not in ("app", "patch"):
        sys.exit("version must be app or patch")
    src = os.path.join(ROOT, "dump", "eboot", version)
    out = os.path.join(ROOT, "build", "eboot", version)
    authid = fself.authid_from_self_auth(os.path.join(src, "self_auth.bin"))
    print(f"authid {authid:#018x}")

    custom = len(sys.argv) > 2
    elf_path = sys.argv[2] if custom else os.path.join(src, "eboot.bin.elf")
    build(elf_path, os.path.join(out, "eboot.bin"), authid, check_sha=not custom)

    for mod in sorted(glob.glob(os.path.join(src, "sce_module", "*.suprx.elf"))):
        name = os.path.basename(mod)[:-len(".elf")]
        build(mod, os.path.join(out, "sce_module", name), authid)


if __name__ == "__main__":
    main()
