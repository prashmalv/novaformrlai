"""
Command line: read a DXF with a vision LLM, build the BOQ with Nova's logic,
and (optionally) score it and the rule-based parser against Nova's quotation.

    python -m src.ai.run DRAWING.dxf --gt QUOTATION.xlsx --panel-height 3200
    python -m src.ai.run DRAWING.dxf --dry-run          # no API call

Every real run is appended to data/ai_runs.jsonl (model, prompt version,
tokens, cost, scores) so models can be compared over time.
"""
import argparse
import contextlib
import datetime
import hashlib
import io
import json
import os
import sys
import time

import ezdxf

from src.ai import prompts
from src.ai.build import build_elements
from src.ai.digest import build_digest
from src.ai.extract import run_overview, run_tiles
from src.ai.groundtruth import load_quotation, score, boq_panel_dict
from src.ai.llm import make_llm, Usage, PRICES, LLMError
from src.ai.render import render_tiles

RUNS_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ai_runs.jsonl")
PROMPT_VERSION = hashlib.sha1(
    (prompts.SYSTEM + prompts.OVERVIEW_TASK + prompts.TILE_TASK + prompts.TILE_EXTRA_NOVA)
    .encode()).hexdigest()[:8]


def _say(msg: str):
    print(msg, flush=True)


def _rule_based(dxf: str, panel_h: float, casting_h: float) -> list:
    """Baseline: the app's current parser, in the same shape as AI predictions."""
    from src.dwg_parse.parse_nova_full import parse_nova_full
    with contextlib.redirect_stdout(io.StringIO()):
        els, boqs, err = parse_nova_full(dxf, product_height_mm=panel_h, casting_height_mm=casting_h)
    return [(b.element.label, b.element.length_mm, b.element.width_mm, boq_panel_dict(b)) for b in boqs]


def _estimate(n_tiles: int, model: str) -> str:
    # ~3.3k tokens per 1568px image; overview is cached after the first tile.
    img = 3300
    inp = img + n_tiles * (img + 2500) + n_tiles * img * 0.1
    out = 2000 + n_tiles * 2500
    p_in, p_out = PRICES.get(model, (0, 0))
    return f"~{inp/1000:.0f}k input + ~{out/1000:.0f}k output tokens ≈ ${(inp*p_in + out*p_out)/1e6:.2f} on {model}"


def _report(path: str, ai_elems: list, scores: dict):
    lines = ["# AI BOQ report", ""]
    for a in ai_elems:
        if a.element is None:
            lines.append(f"- ⚠ skipped ({', '.join(a.checks)}) tiles {a.sources}")
            continue
        e = a.element
        flag = "REVIEW" if a.needs_review else "ok"
        pan = ", ".join(f"{p.size_label}×{p.quantity}" for p in a.boq.panels)
        lines.append(f"- **{e.label}** {e.element_type.value} {e.length_mm}x{e.width_mm} "
                     f"qty {e.quantity} [{flag}] shapes {a.shape_ids} → {pan}")
        for c in a.checks:
            lines.append(f"    - {c}")
        if a.drawn_panels:
            lines.append(f"    - drawn on sheet: {' '.join(a.drawn_panels)}")
    for name, sc in scores.items():
        lines += ["", f"## Score vs quotation — {name}",
                  f"found {sc['found_pct']}% · size ok {sc['size_ok_pct']}% · "
                  f"panels ok {sc['panels_ok_pct']}% of {sc['gt_labels']} labels",
                  f"extra labels not in quotation: {', '.join(sc['extra_labels']) or '-'}", ""]
        for r in sc["rows"]:
            mark = "✓" if r["panels_ok"] else ("~" if r["found"] else "✗")
            lines.append(f"  {mark} {r['label']}: gt {r['gt_size']} {r['gt_panels']} | "
                         f"pred {r['pred_size']} {r['pred_panels']}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="AI-assisted BOQ from a DXF")
    ap.add_argument("dxf")
    ap.add_argument("--gt", help="Nova quotation .xlsx to score against")
    ap.add_argument("--gt-sheet")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                    help="reasoning effort for the overview call")
    ap.add_argument("--tile-effort", default="low", choices=["low", "medium", "high", "xhigh", "max"],
                    help="reasoning effort for each tile (most of the cost)")
    ap.add_argument("--panel-height", type=float, default=3200)
    ap.add_argument("--casting-height", type=float, default=None)
    ap.add_argument("--units", type=float, default=1.0, help="drawing units → mm (1000 if in metres)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", help="output folder (default: ai_out/<drawing name>)")
    ap.add_argument("--dry-run", action="store_true", help="render + estimate cost, no API call")
    a = ap.parse_args(argv)

    name = os.path.splitext(os.path.basename(a.dxf))[0]
    out = a.out or os.path.join("ai_out", name)
    os.makedirs(os.path.join(out, "tiles"), exist_ok=True)
    casting_h = a.casting_height or a.panel_height

    t0 = time.time()
    doc = ezdxf.readfile(a.dxf)
    dg = build_digest(a.dxf, doc, unit_factor=a.units)
    overview_png, tiles = render_tiles(dg, doc)
    with open(os.path.join(out, "tiles", "overview.png"), "wb") as f:
        f.write(overview_png)
    for t in tiles:
        with open(os.path.join(out, "tiles", f"{t.name}.png"), "wb") as f:
            f.write(t.png)
    _say(f"{name}: {len(dg.shapes)} shapes ({len(dg.candidates)} candidates), "
         f"{len(dg.texts)} texts, {len(tiles)} tiles → {out}/tiles  [{time.time() - t0:.0f}s]")

    gt_blocks, scores = None, {}
    if a.gt:
        sheet, gt_blocks = load_quotation(a.gt, a.gt_sheet)
        _say(f"ground truth: sheet {sheet!r}, {sum(len(b.labels) for b in gt_blocks)} labels")
        scores["rule-based"] = score(gt_blocks, _rule_based(a.dxf, a.panel_height, casting_h))

    if a.dry_run:
        _say("dry run, estimate: " + _estimate(len(tiles), a.model))
        if scores:
            sc = scores["rule-based"]
            _say(f"rule-based vs quotation: found {sc['found_pct']}%, size {sc['size_ok_pct']}%, "
                 f"panels {sc['panels_ok_pct']}%")
        return 0

    try:
        llm = make_llm(a.model, a.effort)
        _say(f"stage 1: overview ({a.model}, effort {a.effort})")
        ov, usage = run_overview(llm, dg, overview_png, tiles)
        _say(f"  drawing kind: {ov.drawing_kind}; count from: {ov.count_from}")
        _say(f"stage 2: tiles (effort {a.tile_effort})")
        tile_llm = make_llm(a.model, a.tile_effort)
        tile_res, u2, errors, used = run_tiles(tile_llm, dg, overview_png, tiles, ov,
                                               workers=a.workers, progress=lambda m: _say("  " + m))
    except LLMError as e:
        _say(f"ERROR: {e}")
        return 2
    usage.add(u2)

    findings = [(tn, f) for tn, r in tile_res for f in r.elements]
    schedule = [row for _, r in tile_res for row in r.schedule_rows]
    if ov.floor_or_casting_height_mm and not a.casting_height:
        casting_h = float(ov.floor_or_casting_height_mm)
    ai = build_elements(dg, findings, schedule, a.panel_height, casting_h)

    with open(os.path.join(out, "overview.json"), "w") as f:
        f.write(ov.model_dump_json(indent=1))
    with open(os.path.join(out, "tiles.json"), "w") as f:
        json.dump({tn: r.model_dump() for tn, r in tile_res}, f, indent=1)
    with open(os.path.join(out, "elements.json"), "w") as f:
        json.dump([{
            "label": x.element.label if x.element else None,
            "type": x.element.element_type.value if x.element else None,
            "length": x.element.length_mm if x.element else None,
            "width": x.element.width_mm if x.element else None,
            "qty": x.element.quantity if x.element else 0,
            "panels": boq_panel_dict(x.boq) if x.boq else {},
            "shape_ids": x.shape_ids, "confidence": x.confidence,
            "checks": x.checks, "drawn_panels": x.drawn_panels, "tiles": x.sources,
        } for x in ai], f, indent=1)

    if gt_blocks:
        pred = [(x.element.label, x.element.length_mm, x.element.width_mm, boq_panel_dict(x.boq))
                for x in ai if x.element]
        scores[f"AI {a.model}"] = score(gt_blocks, pred)
    _report(os.path.join(out, "report.md"), ai, scores)

    n_ok = sum(1 for x in ai if x.element and not x.needs_review)
    n_rev = sum(1 for x in ai if x.element and x.needs_review)
    _say(f"\n{len(ai)} element groups: {n_ok} ok, {n_rev} need review, "
         f"{sum(1 for x in ai if not x.element)} skipped; tile errors: {len(errors)}")
    _say(f"tokens: in {usage.input_tokens} (+cache read {usage.cache_read}, write {usage.cache_write}), "
         f"out {usage.output_tokens}; {usage.calls} calls; cost ≈ ${usage.cost_usd(a.model)}; "
         f"{time.time() - t0:.0f}s")
    for nm, sc in scores.items():
        _say(f"{nm:>24}: found {sc['found_pct']:5}%  size ok {sc['size_ok_pct']:5}%  "
             f"panels ok {sc['panels_ok_pct']:5}%  (of {sc['gt_labels']} quotation labels)")
    _say(f"report: {os.path.join(out, 'report.md')}")

    record = {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "drawing": os.path.basename(a.dxf), "model": a.model, "effort": a.effort,
        "tile_effort": a.tile_effort,
        "prompt_version": PROMPT_VERSION, "tiles_sent": len(used), "tile_errors": len(errors),
        "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
        "cache_read": usage.cache_read, "cache_write": usage.cache_write,
        "cost_usd": usage.cost_usd(a.model), "seconds": round(time.time() - t0),
        "elements": len(ai), "needs_review": n_rev,
        "scores": {k: {m: v[m] for m in ("gt_labels", "found_pct", "size_ok_pct", "panels_ok_pct")}
                   for k, v in scores.items()},
    }
    with open(RUNS_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
