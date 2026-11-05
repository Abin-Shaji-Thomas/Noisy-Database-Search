"""
run_experiment.py - runs the full experiment once and saves everything
(plots + CSV) into the results/ folder for the report.

Run:  python run_experiment.py
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")            # save plots to files, no window needed
import matplotlib.pyplot as plt
import numpy as np

import grover as g

PIN = g.DEFAULT_PIN
n = len(PIN)
N = 2 ** n
K_MAX = 8
KS = list(range(K_MAX + 1))
NOISE_LEVELS = [0.0, 0.005, 0.01, 0.02, 0.05]       # CX error rates
FINE_NOISE = [round(x, 4) for x in np.linspace(0, 0.10, 21)]  # for crossover
OUT = "results"
os.makedirs(OUT, exist_ok=True)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=200)
    plt.close(fig)
    print(f"  saved results/{name}")


def bar_colors(keys):
    """Highlight the PIN bar in red, all other bars blue."""
    return ["tab:red" if key == PIN else "tab:blue" for key in keys]


# ---------------------------------------------------------------
# 1. THEORY vs IDEAL SIMULATION
# ---------------------------------------------------------------
k_opt = g.optimal_iterations(n)
theory = [g.theory_success(n, k) for k in KS]
classical = [g.classical_success(n, k) for k in KS]

print(f"\nPIN = {PIN}   n = {n} qubits   N = {N}   k_opt = {k_opt}")
print("Running noise sweep (this takes a few seconds)...")
results = g.sweep(PIN, NOISE_LEVELS, K_MAX)
ideal = results[0.0]

print("\n  k | theory  | ideal sim | classical | diff")
print("  --+---------+-----------+-----------+------")
for k in KS:
    print(f"  {k} | {theory[k]:6.2%} | {ideal[k]:8.2%} | {classical[k]:8.2%} "
          f"| {abs(theory[k] - ideal[k]):.2%}")
max_diff = max(abs(t - s) for t, s in zip(theory, ideal))
ok = max_diff < 0.03
print(f"\n  Max |theory - simulation| = {max_diff:.2%}  ->  "
      f"{'Theory matches simulation (all < 3%)' if ok else 'MISMATCH!'}")

cx, depth = g.gate_counts(PIN)
print(f"\n  One Grover iteration after transpiling: {cx} CX gates, depth {depth}")

print("\nSaving plots:")
fig, ax = plt.subplots(figsize=(8, 5))
k_fine = np.linspace(0, K_MAX, 300)
theta = np.arcsin(1 / np.sqrt(N))
ax.plot(k_fine, np.sin((2 * k_fine + 1) * theta) ** 2, label="Theory sin²((2k+1)θ)")
ax.plot(KS, ideal, "o", ms=8, label="Ideal simulation (2000 shots)")
ax.axvline(k_opt, ls="--", color="grey", label=f"k_opt = {k_opt}")
ax.set(xlabel="Number of Grover iterations k", ylabel="Success probability",
       title=f"Theory vs simulation (PIN {PIN}, N = {N})", ylim=(0, 1.05))
ax.grid(alpha=0.3)
ax.legend()
save(fig, "theory_vs_simulation.png")

# ---------------------------------------------------------------
# 2. MAIN PLOT: success vs iterations for each noise level
# ---------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))
for p2, succ in results.items():
    label = "Ideal (no noise)" if p2 == 0 else f"CX error {p2:.1%}"
    ax.plot(KS, succ, "o-", label=label)
ax.plot(KS, classical, "k--", lw=2, label="Classical search (k+1)/N")
ax.axhline(1 / N, color="grey", ls=":", label=f"Random guess 1/N = {1/N:.2%}")
ax.set(xlabel="Number of Grover iterations k", ylabel="Success probability",
       title=f"Noisy Grover PIN search (PIN {PIN})", ylim=(0, 1.05))
ax.grid(alpha=0.3)
ax.legend()
save(fig, "noisy_success_vs_iterations.png")

# ---------------------------------------------------------------
# 3. HISTOGRAMS at k_opt: ideal vs 1% vs 5% CX error
# ---------------------------------------------------------------
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
all_keys = [format(i, f"0{n}b") for i in range(N)]
for ax, p2 in zip(axes, [0.0, 0.01, 0.05]):
    p, counts = g.run_circuit(PIN, k_opt, p2)
    probs = [counts.get(key, 0) / g.SHOTS for key in all_keys]
    ax.bar(all_keys, probs, color=bar_colors(all_keys))
    name = "Ideal" if p2 == 0 else f"CX error {p2:.0%}"
    ax.set(title=f"{name}: P(PIN) = {p:.1%}", xlabel="Measured state")
    ax.tick_params(axis="x", rotation=90)
    ax.grid(alpha=0.3, axis="y")
axes[0].set_ylabel("Probability")
fig.suptitle(f"Measurement results at k_opt = {k_opt} (red = PIN {PIN})")
save(fig, "histograms_kopt.png")

# ---------------------------------------------------------------
# 4. ADVANTAGE vs NOISE (finer sweep to locate the crossover)
# ---------------------------------------------------------------
fine = g.sweep(PIN, FINE_NOISE, K_MAX)
fine_rows, crossover = g.find_advantage_loss(PIN, fine)

# Classical success at the SAME k that the quantum attacker uses
best = [r["best_success"] for r in fine_rows]
classical_same_k = [classical[r["best_k"]] for r in fine_rows]
p2_pct = [100 * p for p in FINE_NOISE]

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.plot(p2_pct, best, "o-", label="Quantum: best success over k")
ax.plot(p2_pct, classical_same_k, "k--", label="Classical with the same k queries")
ax.axhline(1 / N, color="grey", ls=":", label="Random guess 1/N")
if crossover is not None:
    ax.axvspan(100 * crossover, p2_pct[-1], color="red", alpha=0.12,
               label=f"Advantage lost (CX error > {crossover:.2%})")
    ax.axvline(100 * crossover, color="red", ls="--")
ax.set(xlabel="CX gate error rate p2 (%)", ylabel="Probability",
       title="Where noise cancels the quantum advantage")
ax.grid(alpha=0.3)
ax.legend()
save(fig, "advantage_vs_noise.png")

# ---------------------------------------------------------------
# 5. CIRCUIT DIAGRAM (k = 1)
# ---------------------------------------------------------------
fig = g.build_grover_circuit(PIN, 1).draw("mpl", fold=-1)
save(fig, "circuit.png")

# ---------------------------------------------------------------
# 6. CSV with every number
# ---------------------------------------------------------------
with open(os.path.join(OUT, "results.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["p2", "k", "theory", "simulated", "classical"])
    for p2, succ in results.items():
        for k in KS:
            w.writerow([p2, k, round(theory[k], 4), round(succ[k], 4),
                        round(classical[k], 4)])
print("  saved results/results.csv")

# ---------------------------------------------------------------
# 7. SUMMARY
# ---------------------------------------------------------------
rows, _ = g.find_advantage_loss(PIN, results)
print("\nBest k per noise level:")
print("  CX error | best k | best success | beats classical?")
for r in rows:
    print(f"  {r['p2']:7.1%}  |   {r['best_k']}    |   {r['best_success']:6.2%}    | "
          f"{'yes' if r['advantage'] else 'NO'} (margin {r['margin']:+.2%})")

if crossover is None:
    print("\nQuantum advantage was NOT lost in the tested range (0-10%).")
else:
    print(f"\nQuantum advantage lost at CX error ≈ {crossover:.2%}")
