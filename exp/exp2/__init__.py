"""Exp2 priority-divergence analysis.

Scientific scenario and consequence semantics stay in :mod:`model`.  This
package only summarizes frozen model outputs and evaluates empirical orderings.
"""

from .protocol import BOOTSTRAP_REPLICATES, COMPONENTS, SIMILAR_DELAY_PRIMARY

__all__ = ["BOOTSTRAP_REPLICATES", "COMPONENTS", "SIMILAR_DELAY_PRIMARY"]
