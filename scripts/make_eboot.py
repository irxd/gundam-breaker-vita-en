"""Build a fake-signed eboot.bin (fself) from a FAGDec-decrypted ELF.

  python -I scripts/make_eboot.py [app|patch] [ELF]

Defaults: version "patch" (1.02), ELF dump/eboot/<version>/eboot.bin.elf, authid from
dump/eboot/<version>/self_auth.bin. Output: build/eboot/<version>/eboot.bin
Give a different ELF (e.g. a patched one) as the second argument.
"""
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fself  # noqa: E402


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if version not in ("app", "patch"):
        sys.exit("version must be app or patch")
    src = os.path.join(ROOT, "dump", "eboot", version)
    elf_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(src, "eboot.bin.elf")
    elf = open(elf_path, "rb").read()

    sha_path = os.path.join(src, "eboot.bin.elf.sha256")
    if len(sys.argv) <= 2 and os.path.exists(sha_path):
        if hashlib.sha256(elf).digest() != open(sha_path, "rb").read():
            sys.exit(f"{elf_path} does not match {sha_path}")

    authid = fself.authid_from_self_auth(os.path.join(src, "self_auth.bin"))
    out = fself.make_fself(elf, authid=authid)
    dst = os.path.join(ROOT, "build", "eboot", version, "eboot.bin")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(out)
    print(f"authid {authid:#018x}, {len(elf)} -> {len(out)} bytes: {dst}")


if __name__ == "__main__":
    main()
