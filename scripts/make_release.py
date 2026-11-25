"""Build the English patch and package it as xdelta files (no game data is distributed).

Usage (from the repo root):
    python -I scripts/make_release.py <version>              e.g.  python -I scripts/make_release.py 0.1.0
    python -I scripts/make_release.py <version> --no-build   package the current build/ without rebuilding
    options: --eboot app|patch   which eboot goes into build/rePatch (default patch = 1.02; the release has both)
             --local-zip         also zip build/rePatch for your own testing (game data: never publish it)

Needs xdelta3 (tools/bin/xdelta3.exe, D:/Personal/shin-gundam-musou-en/tools/bin/xdelta3.exe, or on PATH) and the
dump (CLAUDE.md):
    dump/app/PCSG00126/masterPSP2/, finalizedPSP2/   game data. The 1.02 update holds only the eboot and modules,
                                          so all data comes from the base game.
    dump/eboot/{app,patch}/eboot.bin.elf  FAGDec's decrypted eboot of 1.00 and 1.02 (+ self_auth.bin)

Steps:
  1. build (unless --no-build), each step from the pristine dump:
       python -I scripts/build_text.py           -> build/patched/PCSG00126/masterPSP2/GxArchivedFile000/002.dat
       python -E -P scripts/build_images.py      -> the same archives, UI textures replaced (Pillow: -E -P)
       python -I scripts/eboot_text.py build     -> build/eboot/{app,patch}/eboot.bin (fself)
       BUILD_HOOKS (below): python -E -P scripts/build_movies.py
                                                 -> build/patched/PCSG00126/finalizedPSP2/GP/movie/*.usm
  2. lay the result out as rePatch: build/rePatch/PCSG00126/masterPSP2/GxArchivedFile000.dat, 002.dat,
     finalizedPSP2/GP/movie/*.usm (the movies with English subtitles) and eboot.bin
  3. one xdelta per changed file, made from its pristine original, each checked by applying it again:
       masterPSP2/<archive>   from dump/app/PCSG00126/masterPSP2/<archive>
       finalizedPSP2/GP/movie/<name>.usm   from dump/app/PCSG00126/finalizedPSP2/GP/movie/<name>.usm
       eboot.bin              one patch per game version, from FAGDec's eboot.bin.elf of that version (both target
                              rePatch/PCSG00126/eboot.bin; the patchers use whichever ELF the player has)
     xdelta3 -e -9 -S none -A -B 2147483648: no secondary compression and no app header (the web patcher's small
     VCDIFF decoder reads the result), and a source window that covers the whole 1.5 GB archive. Entries shift
     inside the archives, so with a smaller window xdelta cannot find the moved data and the patch gets huge.

Output:
    release/gundam-breaker-en-<version>/       patches/ + manifest.json + checksums.txt + tools/ + README + LICENSE
    release/gundam-breaker-en-<version>.zip    the same, zipped: this is what gets published
    docs/patcher/patches/                      patches + manifest.json for the web patcher (git-ignored; publish
                                               with git add -f)
    release/gundam-breaker-en-<version>-rePatch-LOCAL-ONLY.zip   with --local-zip only. Holds game data.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TID = 'PCSG00126'
NAME = 'gundam-breaker-en'
DUMP = ROOT / 'dump/app' / TID                       # decrypted ux0:app/PCSG00126 (base game 1.00)
PATCHED = ROOT / 'build/patched' / TID / 'masterPSP2'
ARCHIVES = ['GxArchivedFile000.dat', 'GxArchivedFile002.dat']   # the only archives the build changes
MOVIES = ROOT / 'build/patched' / TID / 'finalizedPSP2/GP/movie'   # scripts/build_movies.py output
EBOOTS = {'app': '1.00', 'patch': '1.02'}            # dump/eboot/<key> -> game version
REPATCH = ROOT / 'build/rePatch' / TID
WEB = ROOT / 'docs/patcher/patches'
PLAYER_TOOLS = [ROOT / 'scripts/apply_patches.py', ROOT / 'tools/rename_title.py', ROOT / 'tools/build_sfo.py']
XDELTA_WINDOW = 1 << 31                              # xdelta3's largest source window (2 GiB) > the 1.5 GB archive

# Build steps after text, images and eboot: (description, command). Their output must be laid out in repatch().
BUILD_HOOKS = [
    ('movies (English subtitles; needs ffmpeg: imageio-ffmpeg or $FFMPEG)',
     [sys.executable, '-E', '-P', ROOT / 'scripts/build_movies.py']),
]


def run(*args):
    print('>', ' '.join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT)


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def find_xdelta():
    for p in (ROOT / 'tools/bin/xdelta3.exe', Path('D:/Personal/shin-gundam-musou-en/tools/bin/xdelta3.exe')):
        if p.exists():
            return p
    for name in ('xdelta3', 'xdelta'):
        p = shutil.which(name)
        if p:
            return Path(p)
    sys.exit('xdelta3 not found: put xdelta3.exe in tools/bin/ or on PATH')


def build():
    py = sys.executable
    run(py, '-I', ROOT / 'scripts/build_text.py')
    run(py, '-E', '-P', ROOT / 'scripts/build_images.py')
    run(py, '-I', ROOT / 'scripts/eboot_text.py', 'build')
    for what, cmd in BUILD_HOOKS:
        print(f'build step: {what}')
        run(*cmd)


def repatch(eboot):
    """Copy the built files into build/rePatch/PCSG00126 (the layout the Vita's rePatch plugin reads)."""
    if REPATCH.exists():
        shutil.rmtree(REPATCH)
    (REPATCH / 'masterPSP2').mkdir(parents=True)
    for name in ARCHIVES:
        src = PATCHED / name
        if not src.is_file():
            sys.exit(f'{src} not found: run the build first')
        print(f'copy {src.relative_to(ROOT)}')
        shutil.copyfile(src, REPATCH / 'masterPSP2' / name)
    movies = sorted(MOVIES.glob('*.usm')) if MOVIES.is_dir() else []
    if movies:
        (REPATCH / 'finalizedPSP2/GP/movie').mkdir(parents=True)
        for src in movies:
            shutil.copyfile(src, REPATCH / 'finalizedPSP2/GP/movie' / src.name)
        print(f'copy {len(movies)} movies from {MOVIES.relative_to(ROOT)}')
    src = ROOT / 'build/eboot' / eboot / 'eboot.bin'
    if src.is_file():
        shutil.copyfile(src, REPATCH / 'eboot.bin')
    else:
        print(f'no {src.relative_to(ROOT)}: rePatch folder without eboot.bin')


def xdelta_pair(xdelta, src, dst, patch, tmp):
    """Make src -> dst as patch, then apply it again and check the result."""
    patch.parent.mkdir(parents=True, exist_ok=True)
    run(xdelta, '-e', '-9', '-S', 'none', '-A', '-B', XDELTA_WINDOW, '-f', '-s', src, dst, patch)
    run(xdelta, '-d', '-B', XDELTA_WINDOW, '-f', '-s', src, patch, tmp)
    ok = sha1(tmp) == sha1(dst)
    tmp.unlink()
    if not ok:
        sys.exit(f'{patch.name}: applying the patch does not reproduce {dst}')


def zip_dir(src, zpath, arc_root, store=False):
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in sorted(src.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(arc_root))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('version')
    ap.add_argument('--no-build', action='store_true', help='package build/ as it is')
    ap.add_argument('--eboot', choices=sorted(EBOOTS), default='patch', help='eboot for build/rePatch (default patch)')
    ap.add_argument('--local-zip', action='store_true', help='also zip build/rePatch (game data, local testing only)')
    a = ap.parse_args()
    xdelta = find_xdelta()

    if not a.no_build:
        build()
    repatch(a.eboot)

    out = ROOT / 'release' / f'{NAME}-{a.version}'
    if out.exists():
        shutil.rmtree(out)
    (out / 'patches').mkdir(parents=True)
    tmp = out / 'verify.tmp'
    lines, manifest, skipped = [], [], []

    data = [f'masterPSP2/{name}' for name in ARCHIVES]
    data += sorted(p.relative_to(REPATCH).as_posix() for p in (REPATCH / 'finalizedPSP2').rglob('*.usm'))
    for rel in data:
        src, dst = DUMP / rel, REPATCH / rel
        src_sha, dst_sha = sha1(src), sha1(dst)
        if src_sha == dst_sha:
            skipped.append(rel)
            continue
        xdelta_pair(xdelta, src, dst, out / 'patches' / (rel + '.xdelta'), tmp)
        target = f'rePatch/{TID}/{rel}'
        lines.append(f'{rel}  [app] {src_sha} -> ux0:{target} {dst_sha}')
        entry = {'patch': rel + '.xdelta',
                 'source': {'path': rel, 'origin': 'app', 'size': src.stat().st_size, 'sha1': src_sha},
                 'target': {'path': target, 'size': dst.stat().st_size, 'sha1': dst_sha}}
        if rel.startswith('finalizedPSP2/'):
            entry['optional'] = True        # movies: without them only the movie subtitles stay Japanese
        manifest.append(entry)

    for key, ver in EBOOTS.items():
        src, dst = ROOT / 'dump/eboot' / key / 'eboot.bin.elf', ROOT / 'build/eboot' / key / 'eboot.bin'
        if not (src.is_file() and dst.is_file()):
            print(f'skipping the {ver} eboot: {src} or {dst} not found')
            continue
        patch = f'eboot-{ver}.bin.xdelta'
        xdelta_pair(xdelta, src, dst, out / 'patches' / patch, tmp)
        src_sha, dst_sha = sha1(src), sha1(dst)
        target = f'rePatch/{TID}/eboot.bin'
        lines.append(f'eboot.bin.elf {ver}  [eboot] {src_sha} -> ux0:{target} {dst_sha}')
        manifest.append({'patch': patch,
                         'source': {'path': 'eboot.bin.elf', 'origin': 'eboot', 'gameVersion': ver,
                                    'size': src.stat().st_size, 'sha1': src_sha},
                         'target': {'path': target, 'size': dst.stat().st_size, 'sha1': dst_sha}})

    man = {'version': a.version, 'titleId': TID, 'gameVersions': list(EBOOTS.values()), 'files': manifest}
    (out / 'patches/manifest.json').write_text(json.dumps(man, indent=1) + '\n', encoding='utf-8')
    (out / 'checksums.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'tools').mkdir()
    for p in PLAYER_TOOLS:
        shutil.copy(p, out / 'tools' / p.name)
    for p in ('README.md', 'LICENSE'):
        shutil.copy(ROOT / p, out / p)

    if WEB.exists():
        shutil.rmtree(WEB)
    shutil.copytree(out / 'patches', WEB)

    zpath = out.parent / (out.name + '.zip')
    zip_dir(out, zpath, out.parent)
    print()
    for e in manifest:
        print(f'  {e["patch"]:44} {(out / "patches" / e["patch"]).stat().st_size:>12,} bytes')
    psize = sum(p.stat().st_size for p in (out / 'patches').rglob('*.xdelta'))
    print(f'{len(manifest)} patches ({psize:,} bytes), {len(skipped)} unchanged files skipped {skipped or ""}')
    print(f'wrote {zpath.relative_to(ROOT)} ({zpath.stat().st_size:,} bytes)')
    print(f'web patcher files in {WEB.relative_to(ROOT)}')
    if a.local_zip:
        local = out.parent / f'{out.name}-rePatch-LOCAL-ONLY.zip'
        zip_dir(REPATCH, local, REPATCH.parent.parent, store=True)
        print(f'wrote {local.relative_to(ROOT)} ({local.stat().st_size:,} bytes)  <- game data, local testing only')


if __name__ == '__main__':
    main()
