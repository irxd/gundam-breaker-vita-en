"""Build a test that replaces a few visible lines with English, in place and moved, to check dt2 rebuilding in game.

  python -I scripts/test_dt2_strings.py

Everything else stays original (no tags), so the test lines stand out.
  GP/text/voice_event_text (in every pac bundle that has it), first mission:
    commander "パイロット！　聞こえているか!?"            -> longer English, record MOVED
    commander "機体性能の確認と…行ってもらう！"            -> English in place, with <br>
    operator  "……通信回線、開きます！<br>聞こえますか？"    -> English in place, with <br>
  archive 000 loading tips (000:8a96336f), both copies:
    "ミッション中に高いエースポイントを…"                -> English, record MOVED (forced)
Output: build/test_dt2/PCSG00126/masterPSP2/GxArchivedFile000.dat and 002.dat (001 is unchanged)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dt2  # noqa: E402
import gdat  # noqa: E402
import pac  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
OUT = os.path.join(ROOT, "build", "test_dt2", "PCSG00126", "masterPSP2")

VOICE = "GP/text/voice_event_text"
VOICE_EDITS = {
    "パイロット！　聞こえているか!?":
        ("Pilot! Can you hear me?<br>(Move test: this line is longer than the Japanese and was moved.)", False),
    "機体性能の確認とパイロット適性のテストをかねて<br>敵支配地域周辺部での威力偵察を行ってもらう！":
        ("To test your machine and your aptitude as a pilot,<br>you'll run a recon-in-force near enemy territory!",
         False),
    "……通信回線、開きます！<br>聞こえますか？": ("...Opening the comm line!<br>Can you hear me?", False),
}
TIPS = (0x2C1CF0E2, 0x8A96336F)
TIP_JA = ("ミッション中に高いエースポイントを獲得していると金色の未確認機体が出現する。<br>"
          "強敵であり、出現後一定時間で撤退してしまうが<br>撃破に成功した時には得るものが多い。")
TIP_EN = ("Earn lots of Ace Points in a mission and a gold unknown unit appears.<br>"
          "It's strong and withdraws after a while,<br>but beating it is very rewarding. (move test)")


def apply(payload, edits):
    table = dt2.Dt2(payload)
    hits = []
    for i, k, _, text in list(table.strings()):
        if text in edits:
            en, force = edits[text]
            hits.append((text[:12], table.set_string(i, k, en, force_move=force)))
    # Check: every edited string reads back through the tables.
    check = {t for _, _, _, t in dt2.Dt2(table.to_bytes()).strings()}
    for ja, (en, _) in edits.items():
        if any(h[0] == ja[:12] for h in hits):
            assert en in check, en
    return table.to_bytes(), hits


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)

    path = os.path.join(SRC, "GxArchivedFile002.dat")
    replace = {}
    for h0, h1, _, _, _, data in gdat.iter_entries(path, {"pac"}):
        payload = gdat.unpack(data)
        items = pac.parse(payload)
        changed = False
        for item in items:
            if item[0] == VOICE:
                new, hits = apply(gdat.unpack(item[2]), VOICE_EDITS)
                print(f"002 bundle {h1:08x} {VOICE}: {hits}")
                item[2] = gdat.repack(item[2], new)
                changed = True
        if changed:
            replace[(h0, h1)] = pac.build(items, payload)
    gdat.rebuild(path, os.path.join(OUT, "GxArchivedFile002.dat"), replace)

    path = os.path.join(SRC, "GxArchivedFile000.dat")
    for h0, h1, _, _, _, data in gdat.iter_entries(path, {"dt2"}):
        if (h0, h1) == TIPS:
            new, hits = apply(gdat.unpack(data), {TIP_JA: (TIP_EN, True)})
            print(f"000 tips: {hits}")
            break
    gdat.rebuild(path, os.path.join(OUT, "GxArchivedFile000.dat"), {TIPS: new})
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
