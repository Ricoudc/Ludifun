"""Fabrique les petits sons de l'application (assets/sounds/*.wav), sans aucun enregistrement :
des notes de synthèse douces (sinus et harmonique, attaque et extinction progressives).

    python3 tool/sons.py

Les fichiers sont dans le dépôt ; ce script ne sert qu'à les refaire ou à les changer.
"""

import math
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parents[1] / "assets" / "sounds"

C5, E5, G5, C6, E6, G6 = 523.25, 659.25, 783.99, 1046.5, 1318.5, 1568.0
A4, F4 = 440.0, 349.23


def note(freq: float, seconds: float, volume: float = 0.35) -> list[float]:
    count = int(RATE * seconds)
    samples = []
    for i in range(count):
        t = i / RATE
        attack = min(1.0, t / 0.01)
        release = math.exp(-4.0 * t / seconds)
        tone = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t)
        samples.append(volume * attack * release * tone / 1.25)
    return samples


def sequence(notes: list[tuple[float, float]], gap: float = 0.0) -> list[float]:
    out: list[float] = []
    for freq, seconds in notes:
        out += note(freq, seconds) + [0.0] * int(RATE * gap)
    return out


def write(name: str, samples: list[float]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


write("correct", sequence([(E6, 0.09), (G6, 0.22)]))  # « ding-ding » qui monte
write("partial", sequence([(C6, 0.1), (E6, 0.18)]))
write("wrong", sequence([(A4, 0.12), (F4, 0.22)]))  # deux notes graves, douces : pas un buzzer
write("star", note(C6 * 1.5, 0.08, volume=0.25))
write("finish", sequence([(C5, 0.12), (E5, 0.12), (G5, 0.12), (C6, 0.45)]))  # petite fanfare
