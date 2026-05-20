"""Nonogram solver logic.

Cell state convention (matches the GUI):
    UNKNOWN = 0   -- not yet determined
    BLACK   = 1   -- confirmed filled
    WHITE   = 2   -- confirmed empty

A Board is a 2-D list indexed [row][col].
"""

from __future__ import annotations
import copy

# Cell states
UNKNOWN = 0
BLACK   = 1
WHITE   = 2

Board = list[list[int]]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def solve(
    row_clues: list[list[int]],
    col_clues: list[list[int]],
    initial_board: Board | None = None,
) -> list[Board]:
    """Solve a nonogram and return every unique solution.

    Args:
        row_clues: Row constraints, e.g. [[3], [1, 1], [2]] for a 3-row grid.
        col_clues: Column constraints in the same format.
        initial_board: Optional partially-filled starting state.  If None a
            blank board is used.  Pre-filled BLACK / WHITE cells are treated
            as fixed givens.

    Returns:
        A list of complete boards (no UNKNOWN cells) that satisfy all
        constraints.  Each board is a distinct object.  Returns an empty list
        if no solution exists.
    """
    rows = len(row_clues)
    cols = len(col_clues)

    if initial_board is not None:
        board: Board = copy.deepcopy(initial_board)
    else:
        board = [[UNKNOWN] * cols for _ in range(rows)]

    found: list[Board] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()

    _solve_recursive(board, row_clues, col_clues, found, seen)
    return found


# ---------------------------------------------------------------------------
# Recursive solver
# ---------------------------------------------------------------------------

def _solve_recursive(
    board: Board,
    row_clues: list[list[int]],
    col_clues: list[list[int]],
    found: list[Board],
    seen: set[tuple[tuple[int, ...], ...]],
) -> None:
    """Recursive kernel: deduce, then branch on an unknown cell if needed.

    Args:
        board: Current board state (will be deep-copied before mutation).
        row_clues: Row constraints.
        col_clues: Column constraints.
        found: Accumulator for discovered solutions.
        seen: Set of already-recorded board keys for deduplication.
    """
    # Work on a private copy so sibling branches are independent.
    board = copy.deepcopy(board)

    # ------------------------------------------------------------------
    # Stage 1 — logical deduction
    # Apply deduction rules repeatedly until the board stops changing or
    # a contradiction is found.  Each iteration sweeps every row then
    # every column.
    # ------------------------------------------------------------------
    if not _deduce(board, row_clues, col_clues):
        return  # dead end — current path violates a constraint

    # ------------------------------------------------------------------
    # Check for completion
    # ------------------------------------------------------------------
    if _is_complete(board):
        key = _board_key(board)
        if key not in seen:
            seen.add(key)
            found.append(copy.deepcopy(board))
        return

    # ------------------------------------------------------------------
    # Stage 2 — trial and error
    # The board still has UNKNOWN cells that logic alone cannot resolve.
    # Pick one cell, hypothesise each possible value, and recurse.
    # Each branch independently re-runs Stage 1, which often cascades
    # into many additional deductions before the next branch point.
    # Contradictions are caught by _deduce returning False, pruning that
    # subtree immediately.
    # ------------------------------------------------------------------
    r, c = _pick_branch_cell(board)

    for value in (BLACK, WHITE):
        branch = copy.deepcopy(board)
        branch[r][c] = value
        _solve_recursive(branch, row_clues, col_clues, found, seen)


# ---------------------------------------------------------------------------
# Stage 1 — deduction driver
# ---------------------------------------------------------------------------

def _deduce(
    board: Board,
    row_clues: list[list[int]],
    col_clues: list[list[int]],
) -> bool:
    """Apply all deduction tactics until stable.

    Sweeps rows then columns repeatedly.  Each sweep may unlock further
    deductions in the perpendicular direction, so the loop continues until
    a full sweep produces no new information.

    Args:
        board: Modified in place.
        row_clues: Row constraints.
        col_clues: Column constraints.

    Returns:
        False if a contradiction is detected (board state is unsolvable),
        True otherwise.
    """
    changed = True
    while changed:
        changed = False

        for r, clue in enumerate(row_clues):
            updated = _deduce_line(board[r], clue)
            if updated is None:
                return False
            if updated != board[r]:
                board[r] = updated
                changed = True

        cols = len(col_clues)
        rows = len(board)
        for c, clue in enumerate(col_clues):
            col = [board[r][c] for r in range(rows)]
            updated = _deduce_line(col, clue)
            if updated is None:
                return False
            for r in range(rows):
                if board[r][c] != updated[r]:
                    board[r][c] = updated[r]
                    changed = True

    return True


# ---------------------------------------------------------------------------
# Line-level deduction — orchestrates tactics
# ---------------------------------------------------------------------------

def _deduce_line(line: list[int], clue: list[int]) -> list[int] | None:
    """Apply deduction tactics to a single row or column.

    Tactics are applied in order of cheapness.  Each tactic may fill in
    additional BLACK or WHITE cells; the result is fed into the next tactic.

    Args:
        line: Current cell states for the line (not mutated).
        clue: Block lengths for this line.

    Returns:
        Updated line, or None if the line state contradicts the clue.
    """
    line = list(line)

    # Empty clue: every cell must be white.
    if not clue or clue == [0]:
        if BLACK in line:
            return None
        return [WHITE] * len(line)

    # Quick feasibility check before the more expensive tactics.
    if not _line_is_feasible(line, clue):
        return None

    line = _tactic_overlap(line, clue)
    if line is None:
        return None

    line = _tactic_completion(line, clue)
    if line is None:
        return None

    line = _tactic_edge_anchoring(line, clue)
    if line is None:
        return None

    # Re-validate after all tactics have run.
    if not _line_is_feasible(line, clue):
        return None

    return line


# ---------------------------------------------------------------------------
# Tactics (stubs — to be implemented)
# ---------------------------------------------------------------------------

def _tactic_overlap(line: list[int], clue: list[int]) -> list[int] | None:
    """Deduce cells that are forced BLACK or WHITE across all valid arrangements.

    Algorithm outline:
    1. Left-pack: greedily place each block as far left as possible while
       respecting existing BLACK/WHITE cells.  Record the start index of
       each block in ``left_starts``.
    2. Right-pack: symmetrically place each block as far right as possible.
       Record start indices in ``right_starts``.
    3. If no valid packing exists in either direction, return None.
    4. For block i, the cells in the range
           [right_starts[i],  left_starts[i] + clue[i] - 1]
       are covered by block i in every valid arrangement, so mark them BLACK.
    5. Any cell position not covered by any block in the left-pack AND not
       covered by any block in the right-pack is guaranteed WHITE — mark it.

    This single tactic handles the "overlap" and "complete determination"
    cases described in many nonogram solving guides.

    Returns None if no valid left- or right-packing exists.
    """
    return line  # stub


def _tactic_completion(line: list[int], clue: list[int]) -> list[int] | None:
    """Fill remaining unknowns as WHITE once all BLACK cells are accounted for.

    If the count of BLACK cells in the line already equals sum(clue), every
    UNKNOWN cell must be WHITE.  Also validates that no BLACK run exceeds the
    maximum block length in the clue.

    Returns None on contradiction.
    """
    return line  # stub


def _tactic_edge_anchoring(line: list[int], clue: list[int]) -> list[int] | None:
    """Extend or cap blocks that are anchored against line boundaries or WHITE cells.

    Examples:
    - If cell 0 is BLACK and the first clue is 3, cells 1 and 2 must also be
      BLACK, and cell 3 must be WHITE.
    - If the last two cells are BLACK and the last clue is 2, those cells form
      the final block; the cell immediately before them must be WHITE.

    This is a simplified version of _tactic_overlap restricted to the edges,
    and is cheaper to compute.

    Returns None on contradiction.
    """
    return line  # stub


def _line_is_feasible(line: list[int], clue: list[int]) -> bool:
    """Return False if the partial line provably violates the clue.

    Performs cheap structural checks without enumerating all arrangements:
    - The minimum span of the clue (sum + gaps) must not exceed line length.
    - The number of existing BLACK cells must not exceed sum(clue).
    - No contiguous BLACK run may be longer than the largest block in the clue.
    - The number of remaining UNKNOWN + BLACK cells must be >= sum(clue) minus
      already-placed BLACK cells (enough room for what remains).

    Full arrangement-level consistency is handled by _tactic_overlap.
    """
    return True  # stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_complete(board: Board) -> bool:
    """Return True if every cell is BLACK or WHITE (no UNKNOWN cells remain)."""
    return all(cell != UNKNOWN for row in board for cell in row)


def _pick_branch_cell(board: Board) -> tuple[int, int]:
    """Choose an UNKNOWN cell to branch on during trial-and-error.

    A good heuristic is to pick the cell whose row or column has the fewest
    remaining valid arrangements (most constrained), as this minimises the
    branching factor.  For now, returns the first UNKNOWN cell in reading
    order, which is correct but not optimally efficient.
    """
    for r, row in enumerate(board):
        for c, cell in enumerate(row):
            if cell == UNKNOWN:
                return r, c
    raise ValueError("_pick_branch_cell called on a complete board")


def _board_key(board: Board) -> tuple[tuple[int, ...], ...]:
    """Return a hashable, immutable representation of a board for deduplication."""
    return tuple(tuple(row) for row in board)
