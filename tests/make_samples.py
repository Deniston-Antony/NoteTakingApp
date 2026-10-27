"""Creates a small sample lecture (PDF slides + spoken WAV) in tests/samples for testing."""
import subprocess
from pathlib import Path

import pymupdf

OUT = Path(__file__).parent / "samples"
OUT.mkdir(exist_ok=True)

SLIDES = [
    ("Linear Regression", "Week 3 lecture\n\nModelling the relationship between an input x and an output y"),
    ("The model", "y = w x + b\n\nw: slope (weight)\nb: intercept (bias)\nGoal: choose w and b so the line fits the data"),
    ("Mean squared error", "MSE = (1/n) * sum (y_i - (w x_i + b))^2\n\nMeasures how far predictions are from the true values"),
    ("Gradient descent", "Repeat:\n  w = w - lr * dMSE/dw\n  b = b - lr * dMSE/db\n\nlr = learning rate\nToo big: diverges. Too small: slow."),
]

SPEECH = (
    "Welcome to week three. Today we look at linear regression, which models how an output y depends on an input x. "
    "Our model is a straight line, y equals w times x plus b. The weight w is the slope and b is the intercept. "
    "We want to pick w and b so that the line fits our data as well as possible. "
    "To measure the fit we use the mean squared error. For every point we take the difference between the true value "
    "and our prediction, square it, and average over all points. Smaller error means a better line. "
    "Finally, to find the best w and b we use gradient descent. We repeatedly move w and b a small step "
    "in the direction that lowers the error. The step size is called the learning rate. If it is too large the "
    "error can blow up, and if it is too small training is very slow."
)


def make_pdf():
    doc = pymupdf.open()
    for title, body in SLIDES:
        page = doc.new_page(width=960, height=540)
        page.insert_text((60, 90), title, fontsize=36)
        page.insert_text((60, 160), body, fontsize=22)
    doc.save(OUT / "linear_regression.pdf")


def make_wav():
    wav = OUT / "linear_regression.wav"
    text = SPEECH.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{text}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


if __name__ == "__main__":
    make_pdf()
    make_wav()
    print("samples written to", OUT)
