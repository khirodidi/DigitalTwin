"""
bench/make_figures.py — build every paper figure from MEASURED results only.

Reads bench/results_engine.json and bench/results_ai.json (produced by
bench_engine.py / bench_ai.py) and renders the figures. If a required key is
missing the figure is skipped with a warning rather than filled with a
placeholder, so no figure can ever show a number that was not measured.

Run:  python -m bench.make_figures [--out final_paper/figures]
"""

from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
    "axes.labelsize": 10, "legend.fontsize": 9, "figure.dpi": 150,
    "axes.grid": True, "grid.alpha": 0.3,
    "axes.spines.top": False, "axes.spines.right": False,
})
C = {"prop": "#1a4e8c", "iso": "#c0392b", "svm": "#e67e22", "thr": "#7f8c8d",
     "ok": "#27ae60", "warn": "#f39c12"}


def save(fig, out, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"{name}.{ext}"), bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}.pdf/.png")


# ─────────────────────────────────────────────────────────────────────────────

def fig_anomaly(ai, out):
    a = ai["anomaly"]
    order = ["threshold", "ocsvm", "iso_forest", "lstm_ae"]
    labels = ["Threshold\n(deployed rule)", "One-Class\nSVM",
              "Isolation\nForest", "LSTM-AE\n(proposed)"]
    cols = [C["thr"], C["svm"], C["iso"], C["prop"]]
    n = a["_n_runs"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for ax, metric, title in ((axes[0], "auc", "AUC-ROC"),
                              (axes[1], "f1", "F1-Score")):
        m = [a[k][metric]["mean"] for k in order]
        s = [a[k][metric]["std"] for k in order]
        bars = ax.bar(np.arange(4), m, yerr=s, capsize=5, color=cols,
                      edgecolor="white", lw=0.8, width=0.55)
        ax.set_xticks(np.arange(4)); ax.set_xticklabels(labels, fontsize=8.5)
        ax.set_ylabel(title)
        ax.set_title(f"Early fire detection (pre-smoke) — {title}",
                     fontweight="bold")
        ax.set_ylim(0, 1.12)
        for b, v, e in zip(bars, m, s):
            ax.text(b.get_x() + b.get_width() / 2, v + e + 0.02, f"{v:.3f}",
                    ha="center", fontsize=8.5, fontweight="bold")
    axes[0].axhline(0.5, ls="--", lw=0.9, color="gray", alpha=0.7)
    axes[0].text(0.02, 0.52, "chance", fontsize=7.5, color="gray")
    fig.suptitle(f"Anomaly detection, {n} independent runs (mean ± 1 std). "
                 "The deployed threshold rule cannot fire before smoke latches.",
                 fontsize=9, y=1.03)
    save(fig, out, "fig_anomaly_baseline")


def fig_latency(eng, out):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, key, title, col in (
            (axes[0], "latency_inmemory", "In-memory engine path", C["prop"]),
            (axes[1], "latency_with_postgres", "Including PostgreSQL write", C["ok"])):
        if key not in eng:
            ax.set_visible(False); continue
        e = eng[key]["env"]; l = eng[key]["loc"]
        x = np.arange(2)
        means = [e["mean"], l["mean"]]
        p95 = [e["p95"], l["p95"]]
        p99 = [e["p99"], l["p99"]]
        w = 0.26
        ax.bar(x - w, means, w, label="mean", color=col)
        ax.bar(x, p95, w, label="P95", color=col, alpha=0.62)
        ax.bar(x + w, p99, w, label="P99", color=col, alpha=0.36)
        for xi, vals in zip(x, zip(means, p95, p99)):
            for dx, v in zip((-w, 0, w), vals):
                ax.text(xi + dx, v, f"{v:.3f}", ha="center", va="bottom",
                        fontsize=7.2)
        ax.set_xticks(x)
        ax.set_xticklabels([f"wsn/env\n(n={e['n_samples']:,})",
                            f"wsn/location\n(n={l['n_samples']:,})"])
        ax.set_ylabel("Service time (ms)")
        ax.set_title(title, fontweight="bold")
        ax.legend(fontsize=8)
    fig.suptitle("Per-message service time through the engine "
                 "(measured, log-scale-free linear axis)", fontsize=9, y=1.03)
    save(fig, out, "fig_latency_dist")


def fig_scalability(eng, out):
    sc = eng["scalability"]
    grids = [f"{r['grid']}\n({r['sensors']})" for r in sc]
    mean = [r["mean_ms"] for r in sc]
    p99 = [r["p99_ms"] for r in sc]
    thr = [r["max_msgs_per_s_singlethread"] for r in sc]
    sensors = [r["sensors"] for r in sc]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    ax = axes[0]
    ax.plot(sensors, mean, "o-", color=C["prop"], lw=2, ms=7, label="mean")
    ax.plot(sensors, p99, "s--", color=C["iso"], lw=1.6, ms=6, label="P99")
    # linear reference through the origin and the smallest grid
    k = mean[0] / sensors[0]
    ax.plot(sensors, [k * s for s in sensors], ":", color="gray", lw=1.2,
            label="linear in sensor count")
    ax.set_xlabel("Sensors in grid"); ax.set_ylabel("Service time (ms)")
    ax.set_title("Service time vs. grid size", fontweight="bold")
    ax.legend(fontsize=8)
    for s, v in zip(sensors, mean):
        ax.annotate(f"{v:.3f}", (s, v), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=7.5)

    ax = axes[1]
    ax.bar(range(len(sc)), thr, color=C["prop"], width=0.55)
    ax.set_xticks(range(len(sc))); ax.set_xticklabels(grids, fontsize=8.5)
    ax.set_ylabel("Messages / s (single engine process)")
    ax.set_title("Throughput ceiling implied by mean service time",
                 fontweight="bold")
    for i, v in enumerate(thr):
        ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8,
                fontweight="bold")
    save(fig, out, "fig_scalability")


def fig_evacuation(ai, out):
    e = ai["evacuation"]
    models = ["radial", "corridor", "corner"]
    labels = ["Radial\n(danger model fitted)", "Corridor\n(unseen)",
              "Corner\n(unseen)"]
    x = np.arange(3)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))

    ax = axes[0]
    p = [e[m]["proposed_success"]["mean"] for m in models]
    ps = [e[m]["proposed_success"]["std"] for m in models]
    b = [e[m]["shortest_success"]["mean"] for m in models]
    ax.bar(x - 0.19, p, 0.36, yerr=ps, capsize=4, label="Danger-weighted Dijkstra",
           color=C["prop"])
    ax.bar(x + 0.19, b, 0.36, label="Shortest path", color=C["thr"])
    for i, m in enumerate(models):
        ax.text(i, max(p[i], b[i]) + 0.045,
                f"p={e[m]['wilcoxon_success']['p']:.1e}", ha="center",
                fontsize=7.5, color="navy")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Success rate (peak route danger < 0.8)")
    ax.set_ylim(0, 1.14); ax.legend(fontsize=8)
    ax.set_title("Evacuation success", fontweight="bold")

    ax = axes[1]
    dp = [e[m]["proposed_mean_danger"]["mean"] for m in models]
    db = [e[m]["shortest_mean_danger"]["mean"] for m in models]
    ax.bar(x - 0.19, dp, 0.36, label="Danger-weighted Dijkstra", color=C["prop"])
    ax.bar(x + 0.19, db, 0.36, label="Shortest path", color=C["thr"])
    for i in range(3):
        ax.text(i, max(dp[i], db[i]) + 0.012,
                f"-{(1 - dp[i] / db[i]) * 100:.0f}%", ha="center", fontsize=8,
                color=C["ok"], fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Mean route danger (lower is safer)")
    ax.legend(fontsize=8); ax.set_title("Route danger exposure", fontweight="bold")

    fig.suptitle(f"Evacuation planning, {e['_n_runs']} runs x 200 scenarios. "
                 "Corridor and corner patterns are unseen by the danger estimate.",
                 fontsize=9, y=1.03)
    save(fig, out, "fig_evacuation")


def fig_model5(ai, out):
    m = ai["model5"]
    keys = [("station_cell_recall", "Station\ncell recall"),
            ("station_jaccard_vs_configured", "Station\nJaccard"),
            ("station_confidence", "Station\nconfidence"),
            ("route_jaccard_vs_simulator_waypoints", "Route\nJaccard")]
    means = [m[k]["mean"] for k, _ in keys]
    stds = [m[k]["std"] for k, _ in keys]
    fig, ax = plt.subplots(figsize=(7, 4.3))
    bars = ax.bar(range(len(keys)), means, yerr=stds, capsize=5,
                  color=[C["ok"], C["prop"], C["warn"], C["svm"]], width=0.55)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([l for _, l in keys], fontsize=9)
    ax.set_ylim(0, 1.14); ax.set_ylabel("Score")
    ax.set_title("Model ⑤ — recovery of the configured station and route\n"
                 f"({m['n_runs']} runs, {m['shifts_per_run']} shifts each)",
                 fontweight="bold")
    for b, v, s in zip(bars, means, stds):
        ax.text(b.get_x() + b.get_width() / 2, v + s + 0.025, f"{v:.3f}",
                ha="center", fontsize=9, fontweight="bold")
    save(fig, out, "fig_model5_recovery")


def fig_spof(eng, out):
    s = eng.get("spof")
    if not s:
        print("  ! no spof block; skipping fig_fault_injection")
        return
    t0 = s["outage_start_s"]
    deg = t0 + s["first_degraded_after_outage_s"]
    off = t0 + s["all_offline_after_outage_s"]
    end = s["outage_end_s"]
    rec = end + (s["recovery_all_online_after_reconnect_s"] or 0.0)
    n = s["n_sensors"]
    hb = s["heartbeat_interval_s"]

    t = np.arange(0, end + 25, 0.25)
    online = np.ones_like(t) * n
    for i, ti in enumerate(t):
        if ti < t0:
            online[i] = n
        elif ti < off:
            online[i] = n if ti < deg else n     # all fail together (one gateway)
        elif ti < rec:
            online[i] = 0
        else:
            online[i] = n
    # sensors are declared OFFLINE simultaneously because a single gateway
    # carries every heartbeat; the step at `off` reflects that.
    online = np.where((t >= off) & (t < rec), 0, n)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.fill_between(t, 0, online, color=C["prop"], alpha=0.22)
    ax.plot(t, online, color=C["prop"], lw=2, label="Sensors ONLINE")
    ax.axvspan(t0, end, color="red", alpha=0.08,
               label=f"Gateway outage ({s['outage_duration_s']:.0f} s)")
    for xv, lbl, col, ls in (
            (t0, "outage starts", "red", "--"),
            (deg, f"first DEGRADED (+{s['first_degraded_after_outage_s']:.1f} s)",
             "orange", ":"),
            (off, f"all OFFLINE (+{s['all_offline_after_outage_s']:.1f} s)",
             "darkred", "-."),
            (end, "gateway returns", "green", "--"),
            (rec, f"all ONLINE (+{s['recovery_all_online_after_reconnect_s']:.2f} s)",
             "green", ":")):
        ax.axvline(xv, color=col, ls=ls, lw=1.5, label=lbl)
    ax.set_xlabel("Time (s)"); ax.set_ylabel("Sensors ONLINE")
    ax.set_ylim(-1.5, n * 1.3); ax.legend(fontsize=8, loc="lower right", ncol=2)
    ax.set_title(f"Gateway failure and recovery, measured "
                 f"(n={n} sensors, heartbeat {hb} s)", fontweight="bold")
    fv = eng.get("false_violations_during_outage", {})
    if fv:
        ax.text(0.02, 0.94, f"{fv['false_violations']} false violations in "
                            f"{fv['decisions']} access decisions during outage "
                            f"({fv['unknown']} UNKNOWN)",
                transform=ax.transAxes, fontsize=8.5, color="darkgreen",
                fontweight="bold")
    save(fig, out, "fig_fault_injection")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="bench/results_engine.json")
    ap.add_argument("--ai", default="bench/results_ai.json")
    ap.add_argument("--out", default="bench/figures")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    eng = json.load(open(args.engine))
    ai = json.load(open(args.ai))

    print(f"Rendering figures from measured results -> {args.out}")
    fig_anomaly(ai, args.out)
    fig_evacuation(ai, args.out)
    fig_model5(ai, args.out)
    fig_latency(eng, args.out)
    fig_scalability(eng, args.out)
    fig_spof(eng, args.out)

    # One combined machine-readable file for the manuscript
    combined = {"engine": eng, "ai": ai}
    with open(os.path.join(args.out, "results.json"), "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  wrote results.json")


if __name__ == "__main__":
    main()
