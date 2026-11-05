"""
app.py - simple Gradio web UI. All the quantum work is done in grover.py;
this file only shows the results.

Run:  python app.py   (opens in your browser)
"""

import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import gradio as gr

import grover as g

NOISE_LEVELS = [0.0, 0.005, 0.01, 0.02, 0.05]   # plotted
EXTRA_LEVELS = [0.06, 0.07, 0.08, 0.10]          # only to find the crossover
K_MAX = 8


# ---------------------------------------------------------------
# TAB 1: THEORY (formulas + theory vs ideal simulation table)
# ---------------------------------------------------------------
def theory_markdown(pin=g.DEFAULT_PIN):
    n = len(pin)
    N = 2 ** n
    k_opt = g.optimal_iterations(n)
    lines = [
        f"## Theory for PIN `{pin}` (n = {n} qubits, N = {N})",
        "- Start: H on all qubits → every state has amplitude 1/√N",
        "- Oracle: flips the sign of |PIN⟩  (O = I − 2|PIN⟩⟨PIN|)",
        "- Diffuser: inversion about the mean  (D = 2|s⟩⟨s| − I)",
        "- θ = asin(1/√N), each iteration rotates the state by 2θ",
        "- **P(success after k iterations) = sin²((2k+1)θ)**",
        f"- **Optimal k = ⌊π / 4θ⌋ = {k_opt}** → "
        f"P = {g.theory_success(n, k_opt):.2%}",
        "",
        "| k | Theory | Ideal simulation | Classical (k+1)/N | Difference |",
        "|---|---|---|---|---|",
    ]
    max_diff = 0
    for k in range(K_MAX + 1):
        t = g.theory_success(n, k)
        s = g.run_circuit(pin, k, 0.0)[0]
        max_diff = max(max_diff, abs(t - s))
        lines.append(f"| {k} | {t:.2%} | {s:.2%} | "
                     f"{g.classical_success(n, k):.2%} | {abs(t - s):.2%} |")
    lines.append("")
    if max_diff < 0.03:
        lines.append(f"### Theory matches simulation ✔ (max difference {max_diff:.2%} < 3%)")
    else:
        lines.append(f"### Warning: max difference {max_diff:.2%} is above 3%")
    return "\n".join(lines)


# ---------------------------------------------------------------
# TAB 2: SINGLE RUN
# ---------------------------------------------------------------
def single_run(pin, k, p2_percent):
    pin = (pin or "").strip()
    if not (2 <= len(pin) <= 5) or set(pin) - {"0", "1"}:
        return "❌ PIN must be 2 to 5 characters of only 0 and 1 (e.g. 1011).", None, None

    k = int(k)
    p, counts = g.run_circuit(pin, k, p2_percent / 100)
    n = len(pin)

    # Histogram of all 2^n outcomes, PIN bar in red
    keys = [format(i, f"0{n}b") for i in range(2 ** n)]
    probs = [counts.get(key, 0) / g.SHOTS for key in keys]
    hist, ax = plt.subplots(figsize=(8, 4))
    ax.bar(keys, probs, color=["tab:red" if key == pin else "tab:blue" for key in keys])
    ax.set(xlabel="Measured state", ylabel="Probability",
           title=f"k = {k}, CX error = {p2_percent:.1f}%  (red = PIN)")
    ax.tick_params(axis="x", rotation=90)
    ax.grid(alpha=0.3, axis="y")
    hist.tight_layout()

    circuit = g.build_grover_circuit(pin, k).draw("mpl", fold=-1)

    text = (f"### Success probability: {p:.2%}\n"
            f"Theory (no noise): {g.theory_success(n, k):.2%} · "
            f"Classical attacker (k = {k} queries): {g.classical_success(n, k):.2%}")
    return text, hist, circuit


# ---------------------------------------------------------------
# TAB 3: NOISE vs ITERATIONS (the main answer)
# ---------------------------------------------------------------
def noise_sweep():
    pin = g.DEFAULT_PIN
    n = len(pin)
    N = 2 ** n
    ks = list(range(K_MAX + 1))
    results = g.sweep(pin, NOISE_LEVELS, K_MAX)
    # Extra (higher) noise levels: not plotted, only used to locate the crossover
    extra = g.sweep(pin, EXTRA_LEVELS, K_MAX)
    rows, crossover = g.find_advantage_loss(pin, {**results, **extra})

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for p2, succ in results.items():
        ax.plot(ks, succ, "o-", label="Ideal (no noise)" if p2 == 0 else f"CX error {p2:.1%}")
    ax.plot(ks, [g.classical_success(n, k) for k in ks], "k--", lw=2,
            label="Classical search (k+1)/N")
    ax.axhline(1 / N, color="grey", ls=":", label=f"Random guess 1/N = {1/N:.2%}")
    ax.set(xlabel="Number of Grover iterations k", ylabel="Success probability",
           title=f"Noisy Grover PIN search (PIN {pin})", ylim=(0, 1.05))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()

    lines = ["| CX error | Best k | Best success | Beats classical? |",
             "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['p2']:.1%} | {r['best_k']} | {r['best_success']:.2%} | "
                     f"{'✔ yes' if r['advantage'] else '✘ no'} |")
    if crossover is None:
        lines.append(f"\n### Quantum advantage still present up to "
                     f"{EXTRA_LEVELS[-1]:.0%} CX error")
    else:
        lines.append(f"\n### Quantum advantage lost at CX error ≈ {crossover:.2%}")
    return fig, "\n".join(lines)


# ---------------------------------------------------------------
# BUILD THE UI
# ---------------------------------------------------------------
def load_explanation():
    """Read docs/EXPLANATION.md. Image links are replaced by a short note,
    because the plots are shown in the other tabs."""
    try:
        with open("docs/EXPLANATION.md", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "docs/EXPLANATION.md not found."
    return re.sub(r"!\[(.*?)\]\(\.\./(.*?)\)", r"*(Plot: \1 — see `\2`)*", text)


with gr.Blocks(title="Noisy Grover PIN Search - Team G38") as demo:
    gr.Markdown("# Noisy Database Search with Grover's Algorithm\n"
                "Team G38 · find a secret PIN with Grover's algorithm, "
                "then see how realistic gate noise destroys the quantum advantage.")

    with gr.Tab("Theory"):
        theory_box = gr.Markdown("Calculating theory and simulation...")

    with gr.Tab("Single Run"):
        with gr.Row():
            pin_in = gr.Textbox(value=g.DEFAULT_PIN, label="PIN (2-5 bits, only 0/1)")
            k_in = gr.Slider(0, 8, value=3, step=1, label="Grover iterations k")
            p2_in = gr.Slider(0, 5, value=0, step=0.1, label="CX gate error (%)")
        run_btn = gr.Button("Run Grover", variant="primary")
        result_md = gr.Markdown()
        hist_plot = gr.Plot(label="Measurement histogram")
        circuit_plot = gr.Plot(label="Circuit diagram")
        run_btn.click(single_run, [pin_in, k_in, p2_in],
                      [result_md, hist_plot, circuit_plot])

    with gr.Tab("Noise vs Iterations"):
        gr.Markdown("Runs PIN 1011 for k = 0..8 at CX error 0%, 0.5%, 1%, 2%, 5% "
                    "(plus 6-10% in the background to find where the advantage is lost).")
        sweep_btn = gr.Button("Run noise sweep", variant="primary")
        sweep_plot = gr.Plot(label="Success probability vs iterations")
        sweep_md = gr.Markdown()
        sweep_btn.click(noise_sweep, None, [sweep_plot, sweep_md])

    with gr.Tab("How It Works"):
        gr.Markdown(load_explanation())

    # Fill the Theory tab right after the page opens (keeps start-up fast)
    demo.load(theory_markdown, None, theory_box)


if __name__ == "__main__":
    demo.launch(inbrowser=True)
