"""
Learn Nova's own panel choice per face length from past quotations.

For every rectangular block in a quotation (4 × OC80, no IC, size known) the
flat panels of one set are split back into the two long faces and the two
short faces. When that split is unambiguous, "face length → panels" is one
observation of how Nova actually covers that face (e.g. 450 → 250+200, where
the plain optimizer would pick 350+100).

    python -m src.engine.learn_panel_rules Q1.xlsx Q2.xlsx ... [--out config/panel_face_rules.json]
    python -m src.engine.learn_panel_rules --eval Q1.xlsx ...   # leave-one-file-out check
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from itertools import product

from src.ai.groundtruth import load_quotation

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "panel_face_rules.json")
MAX_GAP = 40        # Nova leaves at most a 40 mm site gap on a face


def _submultisets(counts: dict):
    keys = sorted(counts)
    for picks in product(*[range(counts[k] + 1) for k in keys]):
        yield {k: n for k, n in zip(keys, picks) if n}


def _width_sum(ms: dict) -> int:
    return sum(int(k) * n for k, n in ms.items())


def _combo(ms: dict) -> tuple:
    return tuple(sorted((int(k) for k, n in ms.items() for _ in range(n)), reverse=True))


def split_faces(size: tuple, panels: dict):
    """(long, short), per-set panels → {face_len: combo} or None if ambiguous."""
    flat = {k: v for k, v in panels.items() if k.isdigit()}
    if round(panels.get("OC80", 0)) != 4 or any(k.startswith("IC") for k in panels):
        return None
    long_, short = size
    if long_ == short:
        if any(v % 4 for v in flat.values()):
            return None
        face = {k: int(v // 4) for k, v in flat.items()}
        return {long_: _combo(face)} if long_ - MAX_GAP <= _width_sum(face) <= long_ else None
    if any(v % 2 for v in flat.values()):
        return None
    half = {k: int(v // 2) for k, v in flat.items()}
    found = set()
    for b in _submultisets(half):
        sb = _width_sum(b)
        if not (short - MAX_GAP <= sb <= short):
            continue
        a = {k: half[k] - b.get(k, 0) for k in half if half[k] - b.get(k, 0)}
        if long_ - MAX_GAP <= _width_sum(a) <= long_:
            found.add((_combo(a), _combo(b)))
    if len(found) != 1:
        return None         # no split, or several splits fit -- can't tell
    a, b = found.pop()
    return {long_: a, short: b}


def observations(paths: list) -> list:
    """[(face_len, combo, source)] from every quotation that can be read."""
    out = []
    for p in paths:
        try:
            _, blocks = load_quotation(p)
        except Exception as e:
            print(f"  skip {os.path.basename(p)}: {e}", file=sys.stderr)
            continue
        for blk in blocks:
            if not blk.size:
                continue
            faces = split_faces(blk.size, blk.panels)
            for face, combo in (faces or {}).items():
                out.append((face, combo, os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p)))
    return out


def build_rules(obs: list) -> dict:
    by_face = defaultdict(Counter)
    srcs = defaultdict(set)
    for face, combo, src in obs:
        by_face[face][combo] += 1
        srcs[face].add(src)
    rules = {}
    for face, cnt in sorted(by_face.items()):
        combo, n = cnt.most_common(1)[0]
        rules[str(face)] = {"panels": list(combo), "seen": n,
                            "others": {"+".join(map(str, c)): k for c, k in cnt.items() if c != combo},
                            "sources": sorted(srcs[face])}
    return rules


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("quotations", nargs="+")
    ap.add_argument("--out", default=RULES_PATH)
    ap.add_argument("--eval", action="store_true", help="leave-one-file-out: how often a learned rule predicts an unseen file")
    a = ap.parse_args(argv)

    obs = observations(a.quotations)
    print(f"{len(obs)} face observations from {len({o[2] for o in obs})} quotation files")
    if a.eval:
        from src.engine.panel_optimizer import find_panel_combination
        hit = miss = nocover = base_ok = 0
        for src in sorted({o[2] for o in obs}):
            rules = build_rules([o for o in obs if o[2] != src])
            for face, combo, s in (o for o in obs if o[2] == src):
                plain = tuple(sorted(find_panel_combination(face, use_rules=False)[0], reverse=True))
                base_ok += plain == combo
                r = rules.get(str(face))
                if r is None:
                    nocover += 1
                elif tuple(r["panels"]) == combo:
                    hit += 1
                else:
                    miss += 1
        n = len(obs)
        print(f"plain optimizer matches Nova on {base_ok}/{n} faces")
        print(f"learned rule (from other files): right {hit}, wrong {miss}, no rule yet {nocover}")
        return 0
    rules = build_rules(obs)
    with open(a.out, "w") as f:
        json.dump({"_note": "face length (mm) -> Nova's usual flat panels; learned by "
                            "src/engine/learn_panel_rules.py from past quotations",
                   "rules": rules}, f, indent=1)
    print(f"{len(rules)} face rules → {os.path.relpath(a.out)}")
    for face, r in rules.items():
        print(f"  {face:>5} → {'+'.join(map(str, r['panels']))}  (seen {r['seen']}"
              + (f", also {r['others']}" if r['others'] else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
