"""
Two-stage reading of a drawing with a vision LLM.

Stage 1 (one call): the overview image → what each tile is and which
sheet the element list must come from (stops double counting when one file
holds a client plan, schedules and Nova output copies).
Stage 2 (one call per useful tile, in parallel): tile image + its shape list
→ elements and schedule rows. The overview image sits in the cached prefix,
so every tile after the first pays ~10 % for it.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.ai.digest import Digest, shape_line
from src.ai.llm import Usage, LLMError
from src.ai.prompts import SYSTEM, OVERVIEW_TASK, TILE_TASK, TILE_EXTRA_NOVA
from src.ai.schema import OverviewResult, TileResult

USEFUL_ROLES = ("plan", "schedule", "nova_output")
MAX_TEXTS_PER_TILE = 400


def _tile_of(tiles, x, y) -> str:
    for t in tiles:
        b = t.bounds
        if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
            return t.name
    return "-"


def _big_texts(dg: Digest, tiles, n: int = 40) -> list:
    seen, out = set(), []
    for t in sorted(dg.texts, key=lambda t: -t.height):
        key = t.text.strip().upper()
        if len(key) < 3 or key in seen or key.replace(".", "").isdigit():
            continue
        seen.add(key)
        out.append(f"{_tile_of(tiles, t.x, t.y)}: {t.text[:80]!r}")
        if len(out) >= n:
            break
    return out


def run_overview(llm, dg: Digest, overview_png: bytes, tiles: list):
    text = (OVERVIEW_TASK
            + "\nTiles: " + ", ".join(t.name for t in tiles)
            + "\n\nLargest texts:\n" + "\n".join(_big_texts(dg, tiles)))
    return llm.structured(SYSTEM, [("image", overview_png), ("text", text)],
                          OverviewResult, max_tokens=16000)


def _tile_prompt(dg: Digest, tile, plan, count_from: str) -> str:
    extra = TILE_EXTRA_NOVA if plan.role == "nova_output" else ""
    head = TILE_TASK.format(tile=tile.name, role=plan.role, sheet=plan.sheet,
                            count_from=count_from, extra=extra)
    shapes = "\n".join(shape_line(dg.shape(s)) for s in tile.shape_ids) or "(none)"
    texts = [dg.texts_by_id[i] for i in tile.text_ids]
    listed = texts[:MAX_TEXTS_PER_TILE]
    tlines = "\n".join(f"{t.text[:60]!r} at=({t.x:.0f},{t.y:.0f})" for t in listed)
    more = (f"\n({len(texts) - len(listed)} more texts are visible in the image only)"
            if len(texts) > len(listed) else "")
    return f"{head}\nShapes with red ids in this tile:\n{shapes}\n\nTexts in this tile:\n{tlines}{more}"


def run_tiles(llm, dg: Digest, overview_png: bytes, tiles: list,
              ov: OverviewResult, workers: int = 4, progress=None):
    """Return ([(tile_name, TileResult)], Usage, [error strings])."""
    plans = {p.tile: p for p in ov.tiles}
    # Nova output sheets are kept even when a client plan exists: on CLIENT-1
    # dropping them cut labels found from 100 % to 72 %. Duplicates are merged
    # by label + size in build.py.
    todo = [t for t in tiles if plans.get(t.name) and plans[t.name].role in USEFUL_ROLES]
    prefix = [("image", overview_png),
              ("text", f"Overview decision. Source to count from: {ov.count_from}"),
              ("cache", None)]

    def one(tile):
        parts = prefix + [("image", tile.png),
                          ("text", _tile_prompt(dg, tile, plans[tile.name], ov.count_from))]
        try:
            return tile.name, llm.structured(SYSTEM, parts, TileResult), None
        except LLMError as e:
            return tile.name, None, str(e)

    results, errors, usage = [], [], Usage()
    # First tile alone so it writes the cache; the rest then read it.
    for batch in (todo[:1], todo[1:]):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed([pool.submit(one, t) for t in batch]):
                name, got, err = fut.result()
                if err:
                    errors.append(f"{name}: {err}")
                    if progress:
                        progress(f"tile {name} failed: {err}")
                    continue
                res, u = got
                results.append((name, res))
                usage.add(u)
                if progress:
                    progress(f"tile {name}: {len(res.elements)} elements, "
                             f"{len(res.schedule_rows)} schedule rows")
    return results, usage, errors, [t.name for t in todo]
