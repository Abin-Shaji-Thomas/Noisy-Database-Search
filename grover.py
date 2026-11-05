"""
grover.py - ALL the quantum logic for the "Noisy database search" project.

Problem: find a secret PIN (e.g. "1011") with Grover's algorithm, then run the
same search under a noise model with realistic gate errors and see where the
noise destroys the quantum advantage.

Everything is built BY HAND from basic gates (H, X, multi-controlled X),
so every step of Grover's algorithm can be pointed to in this file.
"""

import math

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

DEFAULT_PIN = "1011"           # 4 qubits -> N = 2^4 = 16 possible PINs
BASIS_GATES = ["cx", "rz", "sx", "x"]   # gates a real IBM-style chip can run
SHOTS = 2000


# =====================================================================
# HELPER: MULTI-CONTROLLED Z (used by both the oracle and the diffuser)
# =====================================================================
def mcz(qc, n):
    """Multi-controlled Z on n qubits: flips the sign of |11...1> only.

    Trick: Z = H X H, so  MCZ = H(last) + MCX(controls -> last) + H(last).
    """
    last = n - 1
    qc.h(last)
    qc.mcx(list(range(last)), last)   # Toffoli-style gate with n-1 controls
    qc.h(last)


# =====================================================================
# ===== STEP 1: INITIALIZATION (Hadamard on all qubits) =====
# =====================================================================
def initialize(qc, n):
    """Put all n qubits in equal superposition |s>.

    After H on every qubit, each of the N = 2^n states has amplitude 1/sqrt(N).
    For n = 4: amplitude = 1/4 = 0.25, probability = 1/16 = 6.25 %.
    """
    for q in range(n):
        qc.h(q)


# =====================================================================
# ===== STEP 2: ORACLE (marks the PIN by flipping its sign) =====
# =====================================================================
def oracle(qc, pin):
    """Oracle O = I - 2|PIN><PIN| : flips the sign of |PIN> only.

    1. X on every qubit where the PIN bit is 0  -> |PIN> becomes |11...1>
    2. Multi-controlled Z                        -> flips sign of |11...1>
    3. Undo the X gates                          -> back to |PIN>, now negative

    IMPORTANT (little-endian): in Qiskit, qubit 0 is the RIGHTMOST bit of the
    result string. So we walk the PIN in reversed order: reversed("1011")
    gives qubit0='1', qubit1='1', qubit2='0', qubit3='1'. This makes the
    measured counts key exactly equal to the PIN string "1011".
    """
    n = len(pin)
    zero_qubits = [q for q, bit in enumerate(reversed(pin)) if bit == "0"]
    for q in zero_qubits:
        qc.x(q)
    mcz(qc, n)
    for q in zero_qubits:
        qc.x(q)


# =====================================================================
# ===== STEP 3: DIFFUSER (inversion about the mean) =====
# =====================================================================
def diffuser(qc, n):
    """Diffuser D = 2|s><s| - I : reflects every amplitude about the mean.

    H all -> X all -> MCZ -> X all -> H all.
    (H maps |s> to |00..0>, X maps |00..0> to |11..1>, MCZ flips its sign,
    then we undo X and H.)  The marked PIN, which is below the mean after
    the oracle, gets pushed far ABOVE the mean -> its probability grows.
    """
    for q in range(n):
        qc.h(q)
    for q in range(n):
        qc.x(q)
    mcz(qc, n)
    for q in range(n):
        qc.x(q)
    for q in range(n):
        qc.h(q)


# =====================================================================
# ===== STEP 4: FULL GROVER CIRCUIT (init + k iterations + measure) =====
# =====================================================================
def build_grover_circuit(pin, k):
    """Init, then k times (oracle + diffuser), then measure all qubits."""
    n = len(pin)
    qc = QuantumCircuit(n)
    initialize(qc, n)
    for _ in range(k):
        qc.barrier()
        oracle(qc, pin)
        qc.barrier()
        diffuser(qc, n)
    qc.measure_all()
    return qc


# =====================================================================
# ===== STEP 5: THEORY (what the maths predicts) =====
# =====================================================================
def theory_success(n, k):
    """Ideal success probability after k iterations: sin^2((2k+1)θ).

    θ = asin(1/sqrt(N)). Every iteration rotates the state by 2θ
    towards the PIN.
    """
    N = 2 ** n
    theta = math.asin(1 / math.sqrt(N))
    return math.sin((2 * k + 1) * theta) ** 2


def optimal_iterations(n):
    """Best number of iterations: floor(π / (4θ))  (≈ (π/4)·sqrt(N))."""
    N = 2 ** n
    theta = math.asin(1 / math.sqrt(N))
    return math.floor(math.pi / (4 * theta))


def classical_success(n, k):
    """Classical attacker with k queries: tries k PINs, then guesses once more.

    Success = (k + 1) / N  (capped at 1).
    """
    N = 2 ** n
    return min((k + 1) / N, 1.0)


# =====================================================================
# ===== STEP 6: NOISE MODEL (realistic gate errors) =====
# =====================================================================
def make_noise_model(p2):
    """Noise model where p2 = error probability of one CX (2-qubit) gate.

    - 1-qubit gates (sx, x): depolarizing error p2/10  (they are ~10x better)
    - 2-qubit gates (cx):    depolarizing error p2
    - Measurement:           2 % chance a bit is read wrong (only if p2 > 0)
    Depolarizing = with probability p the qubit(s) become completely random.
    Returns None for p2 = 0 (ideal, noiseless simulation).
    """
    if p2 <= 0:
        return None
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(p2 / 10, 1), ["sx", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ["cx"])
    nm.add_all_qubit_readout_error(ReadoutError([[0.98, 0.02], [0.02, 0.98]]))
    return nm


# =====================================================================
# ===== STEP 7: RUN ON THE SIMULATOR =====
# =====================================================================
def run_circuit(pin, k, p2=0.0, shots=SHOTS):
    """Build, transpile and simulate. Returns (success_probability, counts).

    Transpiling breaks the big multi-controlled gates into the basic gates
    (cx, rz, sx, x) so the noise model hits every real gate.
    """
    qc = build_grover_circuit(pin, k)
    tqc = transpile(qc, basis_gates=BASIS_GATES, optimization_level=1)
    sim = AerSimulator(noise_model=make_noise_model(p2), seed_simulator=42)
    counts = sim.run(tqc, shots=shots).result().get_counts()
    return counts.get(pin, 0) / shots, counts


# =====================================================================
# ===== STEP 8: SWEEP (success vs iterations, for each noise level) =====
# =====================================================================
def sweep(pin, p2_list, k_max=8):
    """Returns {p2: [success for k = 0, 1, ..., k_max]}."""
    return {p2: [run_circuit(pin, k, p2)[0] for k in range(k_max + 1)]
            for p2 in p2_list}


# =====================================================================
# ===== STEP 9: WHERE DOES NOISE KILL THE QUANTUM ADVANTAGE? =====
# =====================================================================
def find_advantage_loss(pin, results):
    """Analyse the sweep results.

    For each noise level p2:
      best_k, best_success  -> the best number of iterations under noise
      margin  -> max over k >= 1 of (quantum - classical) success
      advantage -> True if quantum beats classical for some k >= 1
    The crossover CX error rate is where the margin crosses 0
    (found by linear interpolation between two neighbouring p2 values).
    Returns (rows, crossover); crossover is None if it never crosses.
    """
    n = len(pin)
    rows = []
    for p2, succ in results.items():
        best_k = max(range(len(succ)), key=lambda k: succ[k])
        margin = max(succ[k] - classical_success(n, k)
                     for k in range(1, len(succ)))
        rows.append({"p2": p2, "best_k": best_k, "best_success": succ[best_k],
                     "margin": margin, "advantage": margin > 0})

    crossover = None
    for a, b in zip(rows, rows[1:]):
        if a["margin"] > 0 >= b["margin"]:
            frac = a["margin"] / (a["margin"] - b["margin"])
            crossover = a["p2"] + frac * (b["p2"] - a["p2"])
            break
    return rows, crossover


# =====================================================================
# ===== STEP 10: GATE COUNT (why noise grows with every iteration) =====
# =====================================================================
def gate_counts(pin):
    """CX count and depth of ONE transpiled Grover iteration (oracle+diffuser)."""
    n = len(pin)
    qc = QuantumCircuit(n)
    oracle(qc, pin)
    diffuser(qc, n)
    tqc = transpile(qc, basis_gates=BASIS_GATES, optimization_level=1)
    return tqc.count_ops().get("cx", 0), tqc.depth()
