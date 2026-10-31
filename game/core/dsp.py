"""Traitements du signal sur des sons bruts (PCM 16 bits signé, voies entrelacées) : filtre passe-bas et écho.

Logique pure, sans carte son : `Audio` s'en sert pour fabriquer, une fois par son, les variantes étouffées (derrière un
mur) ou résonantes (grande salle). Rien n'est précalculé : une variante n'existe que quand on l'entend pour la première fois.
"""
from __future__ import annotations

import math
from array import array
from operator import add

try:  # module C, rapide ; retiré de Python 3.13 : on retombe alors sur le calcul en Python
    import audioop
except ImportError:  # pragma: no cover
    audioop = None

PEAK = 32767


def lowpass(raw: bytes, channels: int, rate: int, cutoff: float) -> bytes:
    """Filtre passe-bas à un pôle (6 dB/octave, appliqué deux fois pour une coupure franche) : le son devient sourd."""
    samples = array("h")
    samples.frombytes(raw)
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / rate)
    out = array("h", samples)
    for c in range(channels):
        first = second = 0.0
        for i in range(c, len(samples), channels):
            first += alpha * (samples[i] - first)
            second += alpha * (first - second)
            out[i] = int(second)
    return out.tobytes()


def echo(raw: bytes, channels: int, rate: int, taps) -> bytes:
    """Ajoute des échos `(délai en s, part du volume)` : la queue prolonge le son du délai le plus long. Sans échos, renvoie `raw`."""
    if not taps or not raw:
        return raw
    pad = max(round(delay * rate) for delay, _ in taps) * channels * 2  # octets : 16 bits
    if audioop is not None:
        mixed = raw + bytes(pad)
        for delay, gain in taps:
            shift = round(delay * rate) * channels * 2
            delayed = bytes(shift) + audioop.mul(raw, 2, gain) + bytes(pad - shift)
            mixed = audioop.add(mixed, delayed, 2)  # additionne en saturant : les sons livrés sont loin du maximum
        return mixed
    samples = array("h")
    samples.frombytes(raw)
    mixed = [float(v) for v in samples] + [0.0] * (pad // 2)
    for delay, gain in taps:
        shift = round(delay * rate) * channels
        scaled = [v * gain for v in samples]
        mixed[shift:shift + len(scaled)] = map(add, mixed[shift:shift + len(scaled)], scaled)
    peak = max(abs(v) for v in mixed)
    scale = PEAK / peak if peak > PEAK else 1.0  # on ramène sous le maximum d'un 16 bits plutôt que de saturer
    return array("h", (int(v * scale) for v in mixed)).tobytes()
