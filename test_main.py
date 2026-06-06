"""Tests for layout-computation logic in main.py.

The central property under test is *canvas-fits-within-window*: for any
window size (win_w, win_h) and grid size (rows x cols), the canvas dimensions
produced by _calc_cell_size + _calc_canvas_dims satisfy:

    input_w + _OVERHEAD_W  <=  win_w
    (input_h + sol_h) + _OVERHEAD_H  <=  win_h

This is what makes root.geometry(win_w x win_h) a complete fix for the resize
cascade.  Once the window is pinned at the settled size the canvas is strictly
smaller, so tkinter's geometry manager cannot drive the window to a different
size and re-trigger the resize handler.

One necessary exception: when the window is so small that cell_size hits its
8 px minimum floor the canvas may overflow, but it cannot shrink any further.
The floor threshold and its stability are verified in separate tests.

No tkinter instance is required; every test exercises pure functions only.
"""

from __future__ import annotations
import math
import pytest

from main import (
    _BASE_CELL,
    _OVERHEAD_H,
    _OVERHEAD_W,
    _calc_canvas_dims,
    _calc_cell_size,
    GRID_LINE_W,
)

_MIN_CELL = 8   # floor enforced by max(8, ...) in _calc_cell_size


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _effective_window(cell_size: int, rows: int, cols: int) -> tuple[int, int]:
    """Smallest window that would fit a canvas built at cell_size (plus overhead).

    This is the size tkinter would shrink the window to if geometry were not
    pinned — i.e. the canvas footprint plus the estimated overhead margins.
    """
    input_w, input_h, _, sol_h = _calc_canvas_dims(cell_size, rows, cols)
    return input_w + _OVERHEAD_W, input_h + sol_h + _OVERHEAD_H


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

# Regression set: real sizes from the Win+Left cascade recorded in the log.
# Each step is the "settled" size that triggered a rebuild in the cascade.
CASCADE_REGRESSION = [
    pytest.param(1536, 841, 9, 12, id="fullscreen_1536x841"),
    pytest.param(768,  841, 9, 12, id="snap_intended_768x841"),
    pytest.param(648,  773, 9, 12, id="snap_actual_648x773"),
    pytest.param(540,  635, 9, 12, id="cascade_1_540x635"),
    pytest.param(450,  520, 9, 12, id="cascade_2_450x520"),
    pytest.param(360,  405, 9, 12, id="cascade_3_360x405"),
    pytest.param(309,  313, 9, 12, id="cascade_4_309x313"),
]

# General coverage: various screen resolutions and grid sizes.
GENERAL = [
    pytest.param(1920, 1080, 9,  12, id="1080p_9x12"),
    pytest.param(1280, 720,  9,  12, id="720p_9x12"),
    pytest.param(2560, 1440, 9,  12, id="1440p_9x12"),
    pytest.param(1920, 1080, 1,  1,  id="1x1_grid"),
    pytest.param(1920, 1080, 5,  5,  id="5x5_grid"),
    pytest.param(1920, 1080, 20, 30, id="20x30_grid"),
    pytest.param(800,  600,  9,  12, id="800x600_9x12"),
    pytest.param(800,  600,  20, 30, id="800x600_20x30"),
    pytest.param(600,  400,  9,  12, id="600x400_9x12"),
]

# Sizes where cell_size must hit the 8 px floor (window too small or grid too large).
FLOOR_CASES = [
    pytest.param(261, 226, 9,  12, id="cascade_end_261x226"),
    pytest.param(273, 244, 9,  12, id="cascade_end_273x244"),
    pytest.param(100, 100, 9,  12, id="tiny_window"),
    pytest.param(1920, 1080, 50, 50, id="50x50_grid_exceeds_1080p"),
]


# ---------------------------------------------------------------------------
# _calc_canvas_dims — correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cell_size, rows, cols, expected", [
    pytest.param(
        57, 1, 1,
        (2 * 57 + GRID_LINE_W, 2 * 57 + GRID_LINE_W,
         1 * 57 + GRID_LINE_W, 1 * 57 + GRID_LINE_W),
        id="base_cell_1x1",
    ),
    pytest.param(
        32, 9, 12,
        # From the log: initial build at 1536x841 produced these canvas sizes.
        (580, 452, 388, 292),
        id="cell32_9x12_from_log",
    ),
    pytest.param(
        26, 9, 12,
        # From the log: rebuild after Win+Left settled at 648x773.
        (472, 368, 316, 238),
        id="cell26_9x12_from_log",
    ),
])
def test_calc_canvas_dims(
    cell_size: int,
    rows: int,
    cols: int,
    expected: tuple[int, int, int, int],
) -> None:
    """_calc_canvas_dims returns the exact pixel dimensions used by the GUI."""
    assert _calc_canvas_dims(cell_size, rows, cols) == expected


# ---------------------------------------------------------------------------
# Canvas fits within window
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("win_w, win_h, rows, cols",
                         CASCADE_REGRESSION + GENERAL + FLOOR_CASES)
def test_canvas_fits_within_window_or_at_floor(
    win_w: int, win_h: int, rows: int, cols: int,
) -> None:
    """After scaling, the canvas fits inside the window, or cell_size is at its floor.

    Both outcomes prevent the cascade:
    - Fits: root.geometry() pins the window; the smaller canvas cannot trigger
      further shrinkage.
    - At floor: the grid cannot scale smaller regardless of window size.

    Any other result (canvas larger than window and cell_size > floor) would mean
    the geometry pin is not sufficient — tkinter would try to grow beyond the
    pinned size, causing Configure events and fresh rebuilds.
    """
    cell_size = _calc_cell_size(win_w, win_h, rows, cols)
    input_w, input_h, _, sol_h = _calc_canvas_dims(cell_size, rows, cols)

    at_floor = cell_size == _MIN_CELL
    fits_w   = input_w + _OVERHEAD_W <= win_w
    fits_h   = (input_h + sol_h) + _OVERHEAD_H <= win_h

    assert at_floor or (fits_w and fits_h), (
        f"canvas {input_w}x{input_h + sol_h} + overhead does not fit in "
        f"window {win_w}x{win_h}, yet cell_size={cell_size} is above the floor"
    )


# ---------------------------------------------------------------------------
# Cascade convergence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("win_w, win_h, rows, cols",
                         CASCADE_REGRESSION + GENERAL + FLOOR_CASES)
def test_cascade_converges(
    win_w: int, win_h: int, rows: int, cols: int,
) -> None:
    """A second scale pass on the canvas-derived window gives cell_size <= first pass.

    Simulates what would happen without geometry pinning: the window shrinks to
    the canvas size, then _calc_cell_size is called again for that smaller window.
    The result must be <= the first cell_size, proving the cascade cannot diverge
    upward and must stabilise (or bottom out at the floor).
    """
    cell_size_1 = _calc_cell_size(win_w, win_h, rows, cols)
    eff_w, eff_h = _effective_window(cell_size_1, rows, cols)
    cell_size_2 = _calc_cell_size(eff_w, eff_h, rows, cols)

    assert cell_size_2 <= cell_size_1, (
        f"cell_size grew: {cell_size_1} -> {cell_size_2} "
        f"(effective window {eff_w}x{eff_h})"
    )


# ---------------------------------------------------------------------------
# Cell size bounds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("win_w, win_h, rows, cols",
                         CASCADE_REGRESSION + GENERAL + FLOOR_CASES)
def test_cell_size_in_valid_range(
    win_w: int, win_h: int, rows: int, cols: int,
) -> None:
    """cell_size is always between the 8 px floor and _BASE_CELL."""
    cell_size = _calc_cell_size(win_w, win_h, rows, cols)
    assert _MIN_CELL <= cell_size <= _BASE_CELL


@pytest.mark.parametrize("rows, cols", [
    pytest.param(1, 1,   id="1x1"),
    pytest.param(5, 5,   id="5x5"),
    pytest.param(9, 12,  id="9x12"),
    pytest.param(15, 20, id="15x20"),
])
def test_large_window_uses_base_cell_size(rows: int, cols: int) -> None:
    """A window much larger than the natural grid size uses the full base cell size."""
    max_row_clues = math.ceil(cols / 2)
    max_col_clues = math.ceil(rows / 2)
    natural_w = (max_row_clues + cols) * _BASE_CELL + _OVERHEAD_W
    natural_h = (max_col_clues + 2 * rows) * _BASE_CELL + _OVERHEAD_H
    cell_size = _calc_cell_size(natural_w * 4, natural_h * 4, rows, cols)
    assert cell_size == _BASE_CELL


# ---------------------------------------------------------------------------
# Floor behaviour
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("win_w, win_h, rows, cols", FLOOR_CASES)
def test_cell_size_at_floor_when_window_too_small(
    win_w: int, win_h: int, rows: int, cols: int,
) -> None:
    """Windows too small (or grids too large) produce exactly the 8 px floor."""
    assert _calc_cell_size(win_w, win_h, rows, cols) == _MIN_CELL


@pytest.mark.parametrize("rows, cols", [
    pytest.param(9, 12, id="9x12"),
    pytest.param(20, 30, id="20x30"),
])
def test_floor_is_a_fixed_point(rows: int, cols: int) -> None:
    """Once cell_size is at the floor, a second pass on the effective window stays at floor.

    This confirms that the cascade bottoms out and cannot loop once the minimum
    cell size is reached, even in the absence of geometry pinning.
    """
    cell_size_1 = _calc_cell_size(10, 10, rows, cols)
    assert cell_size_1 == _MIN_CELL, "precondition: 10x10 window forces floor"

    eff_w, eff_h = _effective_window(cell_size_1, rows, cols)
    cell_size_2 = _calc_cell_size(eff_w, eff_h, rows, cols)
    assert cell_size_2 == _MIN_CELL
