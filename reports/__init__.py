"""Named, opinionated stock reports (tear-sheet / comp-sheet / bull-bear).

Each report consumes price data + indicators + pool metadata
and produces a fixed-format deliverable (HTML / XLSX / PDF).

Pattern borrowed from S&P Global / Daloopa / LSEG Cowork plugins:
clean separation of data layer -> indicator layer -> named report.
"""

from reports.tear_sheet import generate_tear_sheet
from reports.comp_sheet import generate_comp_sheet
from reports.bull_bear import generate_bull_bear

__all__ = [
    "generate_tear_sheet",
    "generate_comp_sheet",
    "generate_bull_bear",
]
