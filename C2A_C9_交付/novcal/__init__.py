"""
NovCal — A Procedurally-Generated Metacognition Benchmark
==========================================================

Track 2 (Metacognition) entry for the DeepMind / Kaggle
"Measuring Progress Toward AGI" hackathon.

The question NovCal asks is not "can the model solve this?" but
"does the model know that it solved it?"

Quick start
-----------
    python -m novcal.cli run --solver baseline --n-universes 20
    python -m novcal.cli selftest
"""

from .rules import (
    Universe,
    generate_universe,
    parse_sequence,
    render_sequence,
    sample_input,
)
from .metrics import (
    CalibrationReport,
    auroc,
    aurc,
    brier_score,
    build_report,
    expected_calibration_error,
    parse_confidence,
)
from .harness import (
    Interaction,
    Item,
    ProtocolConfig,
    build_interactions,
    run_benchmark,
    score_response,
    solver_from_callables,
    split_answer_confidence,
    summarise,
)

__version__ = "1.0.0"

__all__ = [
    "Universe", "generate_universe", "parse_sequence", "render_sequence",
    "sample_input",
    "CalibrationReport", "auroc", "aurc", "brier_score", "build_report",
    "expected_calibration_error", "parse_confidence",
    "Interaction", "Item", "ProtocolConfig", "build_interactions",
    "run_benchmark", "score_response", "solver_from_callables",
    "split_answer_confidence", "summarise",
]