#!/usr/bin/env python3
"""
Build the Phase 1 generalization scorecard and catastrophic-forgetting table.

Reads the frozen baseline results and every phase1_*.json produced by
eval_checkpoint.py, and emits one machine-readable comparison plus a markdown
table. Failed experiments are included — nothing is filtered out.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BASELINE_SOURCES = {
    "alpha_asvspoof_eval": ("evaluation/results/asvspoof_official/results.json",
                            "test_split"),
    "beta_mlaad_tiny": ("evaluation/results/mlaad_ood/results.json",
                        "test_unseen_generators"),
    "gamma_wavefake": ("evaluation/results/wavefake_ood/results.json",
                       "test_unseen_vocoders"),
    "delta_in_the_wild": ("evaluation/results/inthewild_delta_baseline/results.json",
                          "test"),
}
ORDER = ["alpha_asvspoof_eval", "beta_mlaad_tiny", "gamma_wavefake", "delta_in_the_wild"]
LABEL = {"alpha_asvspoof_eval": "ASVspoof α", "beta_mlaad_tiny": "MLAAD-tiny β",
         "gamma_wavefake": "WaveFake γ", "delta_in_the_wild": "In-the-Wild δ"}


def baseline() -> dict:
    out = {}
    for name, (path, key) in BASELINE_SOURCES.items():
        d = json.load(open(REPO / path))[key]
        m = d.get("summary_at_eer_threshold") or d.get("summary_at_asvspoof_dev_eer")
        out[name] = {
            "roc_auc": m["roc_auc"],
            "eer": d["own_eer_reference_only"]["eer"],
            "far": m["far"], "frr": m["frr"],
            "tpr": m["tpr"], "tnr": m["tnr"],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="evaluation/results/phase1_scorecard.json")
    ap.add_argument("--md", default="experiments/phase1_aasist/reports/scorecard.md")
    args = ap.parse_args()

    base = baseline()
    models = {"frozen_aasist_l_baseline": base}
    for f in sorted(glob.glob(str(REPO / "evaluation/results/phase1_*.json"))):
        if "scorecard" in f:
            continue
        d = json.load(open(f))
        row = {}
        for name, e in d["results"].items():
            m = e["at_own_eer_threshold"]
            row[name] = {"roc_auc": m["roc_auc"],
                         "eer": e["own_eer_reference_only"]["eer"],
                         "far": m["far"], "frr": m["frr"],
                         "tpr": m["tpr"], "tnr": m["tnr"]}
        models[d["model_version"]] = row

    deltas = {}
    for mv, row in models.items():
        if mv == "frozen_aasist_l_baseline":
            continue
        deltas[mv] = {n: {f"d_{k}": round(row[n][k] - base[n][k], 4)
                          for k in ("roc_auc", "eer", "far", "frr")}
                      for n in row if n in base}

    payload = {"baseline": base, "models": models, "deltas_vs_baseline": deltas}
    (REPO / args.out).write_text(json.dumps(payload, indent=2, default=float))

    lines = ["# Phase 1 Generalization Scorecard", "",
             "All rows measured on the identical frozen manifests, cascade disabled,",
             "`prep-v1` preprocessing. EER is each set's own EER (reference only).", "",
             "| Model | " + " | ".join(f"{LABEL[n]} AUC | {LABEL[n]} EER" for n in ORDER) + " |",
             "|---" * (1 + 2 * len(ORDER)) + "|"]
    for mv, row in models.items():
        cells = []
        for n in ORDER:
            if n in row:
                cells += [f"{row[n]['roc_auc']:.4f}", f"{row[n]['eer']*100:.2f}%"]
            else:
                cells += ["—", "—"]
        lines.append(f"| {mv} | " + " | ".join(cells) + " |")

    lines += ["", "## Catastrophic-forgetting deltas vs frozen AASIST-L", "",
              "| Model | Set | ΔAUC | ΔEER | ΔFAR | ΔFRR |", "|---|---|---|---|---|---|"]
    for mv, row in deltas.items():
        for n in ORDER:
            if n not in row:
                continue
            d = row[n]
            lines.append(f"| {mv} | {LABEL[n]} | {d['d_roc_auc']:+.4f} | "
                         f"{d['d_eer']:+.4f} | {d['d_far']:+.4f} | {d['d_frr']:+.4f} |")
    (REPO / args.md).parent.mkdir(parents=True, exist_ok=True)
    (REPO / args.md).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
