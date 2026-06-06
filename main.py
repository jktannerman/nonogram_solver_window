#!/usr/bin/env python3
"""Nonogram solver -- GUI for grid input and visualisation."""

from __future__ import annotations
import json
import logging
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from solver import solve

# -- Colours ------------------------------------------------------------------
COLOR_BLACK   = "#616161"   # confirmed matching (filled)
COLOR_WHITE   = "#F8F8F8"   # confirmed non-matching (empty)
COLOR_UNKNOWN = "#ADADAD"   # unknown (halfway between the two)
COLOR_GRID    = "#9CACB5"   # grid lines
COLOR_BG      = "#C8C8C8"   # window background
COLOR_CLUE_BG = "#E8E8E8"   # clue entry background

STATE_COLORS: dict[int, str] = {
    0: COLOR_UNKNOWN,
    1: COLOR_BLACK,
    2: COLOR_WHITE,
}

# -- Base layout values (scaled per grid at runtime) --------------------------
_BASE_CELL  = 57   # px per grid square at 1× scale (clue boxes match this)
GRID_LINE_W = 4    # px; not scaled

# -- Estimated fixed overhead *inside* the window (divider, padding) ---------
# winfo_height() already excludes the OS title bar and taskbar.
# Buttons are now side-by-side with grids, so only the divider and padding
# remain as vertical overhead.  Horizontal overhead accounts for the side
# button panel (~100 px) plus container padding.
_OVERHEAD_H = 40   # px; divider + vertical padding
_OVERHEAD_W = 120  # px; side button panel + horizontal padding


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

_RECORD_BUILT_INS = frozenset(vars(logging.makeLogRecord({})))


class _JsonFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "ms": int(record.msecs),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, val in record.__dict__.items():
            if key not in _RECORD_BUILT_INS and not key.startswith("_"):
                obj[key] = val
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logger: JSON to file (DEBUG+) only."""
    log_path = Path(__file__).parent / "nonogram.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_JsonFormatter())
    root.addHandler(fh)


log = logging.getLogger(__name__)


class NonogramApp:
    """Top-level controller for the Nonogram Solver.

    Args:
        root: The root Tk window.
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Nonogram Solver")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(True, True)

        self.rows: int = 0
        self.cols: int = 0
        self.grid_state: list[list[int]] = []
        self.cell_rects: dict[tuple[int, int], int] = {}

        # Clue widgets indexed [row_or_col_index][box_index]
        self.row_clue_entries: list[list[tk.Entry]] = []
        self.col_clue_entries: list[list[tk.Entry]] = []

        # Computed from grid size in _build_grid_ui
        self._row_clue_w: int = 0
        self._col_clue_h: int = 0
        self._max_row_clues: int = 0
        self._max_col_clues: int = 0

        # Scaled layout values — updated by _compute_scale() each build
        self._cell_size: int = _BASE_CELL
        self._clue_box_size: int = _BASE_CELL
        self._clue_font: tuple[str, int] = ("Consolas", 12)

        self._current_frame: tk.Widget | None = None
        self.canvas: tk.Canvas | None = None

        # Solution display state
        self._solutions: list[list[list[int]]] = []
        self._solution_idx: int = 0
        self._solution_canvas: tk.Canvas | None = None
        self._solution_label: tk.StringVar | None = None
        self._sol_cell_rects: dict[tuple[int, int], int] = {}
        self._prev_btn: tk.Button | None = None
        self._next_btn: tk.Button | None = None

        # Resize debouncing
        self._resize_job: str | None = None
        self._last_win_size: tuple[int, int] = (0, 0)

        log.info("NonogramApp initialised")
        self._show_setup()
        self.root.bind("<Configure>", self._on_root_configure)

    # -- Resize handling ------------------------------------------------------

    def _on_root_configure(self, event: tk.Event) -> None:
        """Debounce window resize events; ignore non-root and no-op events."""
        if event.widget is not self.root or self.rows == 0:
            return
        new_size = (event.width, event.height)
        if new_size == self._last_win_size:
            return
        log.debug(
            f"window resizing to {event.width}x{event.height}",
            extra={
                "from_w": self._last_win_size[0],
                "from_h": self._last_win_size[1],
                "to_w": event.width,
                "to_h": event.height,
            },
        )
        self._last_win_size = new_size
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(150, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        """Rebuild the grid UI at the new window size, preserving all state."""
        self._resize_job = None
        win_w = self.root.winfo_width()
        win_h = self.root.winfo_height()
        # Pin the window at the settled size so tkinter's geometry manager cannot
        # shrink it to fit the new (smaller) canvas after the rebuild.
        self.root.geometry(f"{win_w}x{win_h}")
        log.info(
            f"resize settled at {win_w}x{win_h} — rebuilding UI",
            extra={"win_w": win_w, "win_h": win_h, "rows": self.rows, "cols": self.cols},
        )

        row_vals, col_vals = self._save_entry_clues()
        log.debug(
            "clue values saved",
            extra={"row_clue_boxes": sum(len(r) for r in row_vals),
                   "col_clue_boxes": sum(len(c) for c in col_vals)},
        )

        saved_state = [row[:] for row in self.grid_state]
        saved_solutions = self._solutions
        saved_idx = self._solution_idx

        self._build_grid_ui()
        log.debug("grid UI rebuilt after resize")

        self.grid_state = saved_state
        self._sync_grid_colors()

        self._restore_entry_clues(row_vals, col_vals)
        log.debug("clue values and grid state restored")

        if saved_solutions:
            self._solutions = saved_solutions
            self._show_solution(saved_idx)
            log.debug(
                "solution display restored",
                extra={"solution_idx": saved_idx, "total": len(saved_solutions)},
            )

    def _save_entry_clues(self) -> tuple[list[list[str]], list[list[str]]]:
        """Return the raw text of every clue entry widget."""
        if not self.row_clue_entries:
            return [], []
        row_vals = [[e.get() for e in row] for row in self.row_clue_entries]
        col_vals = [[e.get() for e in col] for col in self.col_clue_entries]
        return row_vals, col_vals

    def _restore_entry_clues(
        self,
        row_vals: list[list[str]],
        col_vals: list[list[str]],
    ) -> None:
        """Write saved clue text back into the freshly-created entry widgets."""
        for row_entries, vals in zip(self.row_clue_entries, row_vals):
            for entry, val in zip(row_entries, vals):
                entry.delete(0, tk.END)
                entry.insert(0, val)
        for col_entries, vals in zip(self.col_clue_entries, col_vals):
            for entry, val in zip(col_entries, vals):
                entry.delete(0, tk.END)
                entry.insert(0, val)

    def _sync_grid_colors(self) -> None:
        """Repaint input grid cells to match self.grid_state after a rebuild."""
        assert self.canvas is not None
        cells = self.rows * self.cols
        log.debug("syncing input grid colors", extra={"cells": cells})
        for r in range(self.rows):
            for c in range(self.cols):
                self.canvas.itemconfig(
                    self.cell_rects[(r, c)],
                    fill=STATE_COLORS[self.grid_state[r][c]],
                )

    # -- Setup screen ---------------------------------------------------------

    def _show_setup(self) -> None:
        """Display the grid-size input form."""
        if self._current_frame is not None:
            self._current_frame.destroy()
        self.canvas = None
        self._solution_canvas = None

        log.info("showing setup screen")

        frame = tk.Frame(self.root, padx=40, pady=40, bg=COLOR_BG)
        frame.pack(fill="both", expand=True)
        self._current_frame = frame

        tk.Label(
            frame, text="Nonogram Solver",
            font=("Segoe UI", 18, "bold"), bg=COLOR_BG,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 24))

        tk.Label(frame, text="Rows:", bg=COLOR_BG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="e", padx=8)
        self._rows_var = tk.StringVar(value="9")
        rows_entry = tk.Entry(frame, textvariable=self._rows_var, width=6,
                              font=("Segoe UI", 10))
        rows_entry.grid(row=1, column=1, sticky="w")

        tk.Label(frame, text="Columns:", bg=COLOR_BG,
                 font=("Segoe UI", 10)).grid(row=2, column=0, sticky="e", padx=8, pady=8)
        self._cols_var = tk.StringVar(value="12")
        tk.Entry(frame, textvariable=self._cols_var, width=6,
                 font=("Segoe UI", 10)).grid(row=2, column=1, sticky="w")

        tk.Button(
            frame, text="Generate Grid",
            font=("Segoe UI", 10), command=self._on_generate, padx=8, pady=4,
        ).grid(row=3, column=0, columnspan=2, pady=(16, 0))

        rows_entry.focus_set()
        self.root.bind("<Return>", lambda _e: self._on_generate())

    def _on_generate(self) -> None:
        """Validate size inputs and transition to the grid view."""
        try:
            rows = int(self._rows_var.get())
            cols = int(self._cols_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Rows and columns must be whole numbers.")
            return
        if not (1 <= rows <= 50 and 1 <= cols <= 50):
            messagebox.showerror("Out of range", "Rows and columns must each be between 1 and 50.")
            return

        log.info("generating grid", extra={"rows": rows, "cols": cols})
        self.root.unbind("<Return>")
        self.rows = rows
        self.cols = cols
        self.grid_state = [[0] * cols for _ in range(rows)]
        self._build_grid_ui()

    # -- Scale computation ----------------------------------------------------

    def _compute_scale(self) -> None:
        """Set _cell_size / _clue_box_size / _clue_font to fit the current window.

        Uses the actual window dimensions (updated via update_idletasks) so the
        result is correct whether the window is maximized, restored, or resized.
        Scale is capped at 1× so small grids keep their natural size.  A small
        safety factor (0.92) guards against imprecision in the overhead estimate.
        """
        win_h = self.root.winfo_height()
        win_w = self.root.winfo_width()

        # Combined natural height of both canvases at 1× scale.
        # Clue boxes are the same size as grid cells, so everything uses _BASE_CELL.
        #   top    = column-clue strip + grid rows
        #   bottom = grid rows only (no clue area above it)
        combined_h = (self._max_col_clues + 2 * self.rows) * _BASE_CELL

        # Top canvas is wider (includes row-clue strip), so it sets the width limit.
        top_w = (self._max_row_clues + self.cols) * _BASE_CELL

        avail_h = win_h - _OVERHEAD_H
        avail_w = win_w - _OVERHEAD_W

        raw_s = min(avail_h / combined_h, avail_w / top_w)
        s = min(raw_s, 1.0)
        if s < 1.0:
            s *= 0.92   # safety margin only when scaling down

        self._cell_size     = max(8, int(_BASE_CELL * s))
        self._clue_box_size = self._cell_size   # clue slots match grid cells exactly
        # Target ~75 % of the entry height (cell_size − 4 px); 1 pt ≈ 1.33 px on 96 DPI.
        font_pt             = max(6, int((self._cell_size - 4) * 0.75 / 1.333))
        self._clue_font     = ("Consolas", font_pt)

        log.debug(
            "scale computed",
            extra={
                "win_w": win_w,
                "win_h": win_h,
                "avail_w": avail_w,
                "avail_h": avail_h,
                "raw_scale": round(raw_s, 4),
                "applied_scale": round(s, 4),
                "cell_size": self._cell_size,
                "font_pt": font_pt,
            },
        )

    # -- Grid screen ----------------------------------------------------------

    def _build_grid_ui(self) -> None:
        """Build the interactive nonogram grid (top half) and solution panel (bottom half)."""
        # Flush pending geometry events before destroying content so _compute_scale
        # reads the correct window dimensions rather than a collapsed intermediate state.
        self.root.update_idletasks()
        if self._current_frame is not None:
            self._current_frame.destroy()

        self._max_row_clues = math.ceil(self.cols / 2)
        self._max_col_clues = math.ceil(self.rows / 2)
        self._compute_scale()
        self._row_clue_w = self._max_row_clues * self._clue_box_size
        self._col_clue_h = self._max_col_clues * self._clue_box_size

        total_w = self._row_clue_w + self.cols * self._cell_size + GRID_LINE_W
        total_h = self._col_clue_h + self.rows * self._cell_size + GRID_LINE_W

        log.info(
            "building grid UI",
            extra={
                "rows": self.rows,
                "cols": self.cols,
                "cell_size": self._cell_size,
                "canvas_w": total_w,
                "canvas_h": total_h,
                "max_row_clues": self._max_row_clues,
                "max_col_clues": self._max_col_clues,
            },
        )

        outer = tk.Frame(self.root, bg=COLOR_BG)
        outer.pack(fill="both", expand=True)
        self._current_frame = outer

        # ---- Top half: input grid -------------------------------------------
        top_frame = tk.Frame(outer, bg=COLOR_BG)
        top_frame.pack(fill="x")

        # Canvas and its right-side buttons travel together as a centered unit.
        top_container = tk.Frame(top_frame, bg=COLOR_BG)
        top_container.pack(anchor="center", pady=(6, 4))

        self.canvas = tk.Canvas(
            top_container,
            width=total_w,
            height=total_h,
            bg=COLOR_BG,
            highlightthickness=0,
        )
        self.canvas.pack(side="left")

        # Right-side panel: New Grid at top, Solve anchored to the bottom.
        # takefocus=False keeps buttons out of the Tab cycle so focus stays on entries.
        top_btn = tk.Frame(top_container, bg=COLOR_BG)
        top_btn.pack(side="left", fill="y", padx=(8, 0))
        tk.Button(top_btn, text="New Grid", command=self._show_setup,
                  font=("Segoe UI", 9), takefocus=False).pack(side="top", anchor="nw")
        tk.Button(top_btn, text="Solve", command=self._on_solve,
                  font=("Segoe UI", 9), takefocus=False).pack(side="bottom", anchor="sw")

        self._draw_cells()
        self._draw_grid_lines()
        self._create_clue_widgets()

        self.canvas.bind("<Button-1>", self._on_click)

        # ---- Divider --------------------------------------------------------
        tk.Frame(outer, height=3, bg=COLOR_GRID).pack(fill="x")

        # ---- Bottom half: solution display ----------------------------------
        self._solutions = []
        self._solution_idx = 0
        self._build_solution_panel(outer)

        log.debug(
            "grid UI build complete",
            extra={"rows": self.rows, "cols": self.cols, "cell_size": self._cell_size},
        )

    def _draw_cells(self) -> None:
        """Draw all grid cells as filled rectangles without outlines."""
        assert self.canvas is not None
        self.cell_rects = {}
        count = self.rows * self.cols
        log.debug("drawing input grid cells", extra={"rows": self.rows, "cols": self.cols, "count": count})
        for r in range(self.rows):
            for c in range(self.cols):
                x0 = self._row_clue_w + c * self._cell_size
                y0 = self._col_clue_h + r * self._cell_size
                rect_id = self.canvas.create_rectangle(
                    x0, y0,
                    x0 + self._cell_size, y0 + self._cell_size,
                    fill=COLOR_UNKNOWN,
                    outline="",
                )
                self.cell_rects[(r, c)] = rect_id

    def _draw_grid_lines(self) -> None:
        """Draw grid lines over the cell area and clue-area separators."""
        assert self.canvas is not None
        gx = self._row_clue_w
        gy = self._col_clue_h
        x_end = gx + self.cols * self._cell_size
        y_end = gy + self.rows * self._cell_size

        h_lines = self.rows + 1
        v_lines = self.cols + 1
        log.debug(
            "drawing input grid lines",
            extra={
                "h_lines": h_lines,
                "v_lines": v_lines,
                "clue_separators": 2,
                "total_lines": h_lines + v_lines + 2,
            },
        )

        for r in range(self.rows + 1):
            y = gy + r * self._cell_size
            self.canvas.create_line(gx, y, x_end, y, fill=COLOR_GRID, width=GRID_LINE_W)

        for c in range(self.cols + 1):
            x = gx + c * self._cell_size
            self.canvas.create_line(x, gy, x, y_end, fill=COLOR_GRID, width=GRID_LINE_W)

        self.canvas.create_line(gx, 0, gx, y_end, fill=COLOR_GRID, width=GRID_LINE_W)
        self.canvas.create_line(0, gy, x_end, gy, fill=COLOR_GRID, width=GRID_LINE_W)

    def _create_clue_widgets(self) -> None:
        """Embed Entry widgets for row and column clues with keyboard navigation.

        Row clues: ceil(cols/2) boxes per row, left-to-right.
          Right → next box; Left → previous box; Down → row below; Up → row above.
        Column clues: ceil(rows/2) boxes per column, top-to-bottom.
          Down → next box; Up → previous box; Right → column to the right; Left → column to the left.

        Tab cycles through all row entries then all column entries, wrapping from
        the last column box back to the first row box.
        """
        assert self.canvas is not None
        # Entries fill nearly the full cell slot; the 4 px gap matches GRID_LINE_W.
        ew = max(8, self._cell_size - 4)

        row_entry_count = self.rows * self._max_row_clues
        col_entry_count = self.cols * self._max_col_clues
        log.debug(
            "creating clue entry widgets",
            extra={
                "row_entries": row_entry_count,
                "col_entries": col_entry_count,
                "total_entries": row_entry_count + col_entry_count,
                "entry_px": ew,
            },
        )

        # Row clue entries — created first so they appear first in Tab order.
        self.row_clue_entries = []
        for r in range(self.rows):
            y_mid = self._col_clue_h + r * self._cell_size + self._cell_size // 2
            row_entries: list[tk.Entry] = []
            for k in range(self._max_row_clues):
                x_mid = k * self._cell_size + self._cell_size // 2
                entry = tk.Entry(
                    self.canvas, justify="center",
                    font=self._clue_font, relief="ridge", bg=COLOR_CLUE_BG, width=2,
                )
                self.canvas.create_window(x_mid, y_mid, window=entry, width=ew, height=ew)
                entry.bind("<Right>",    lambda e, _r=r, _k=k: self._row_focus_right(_r, _k) or "break")
                entry.bind("<Left>",     lambda e, _r=r, _k=k: self._row_focus_left(_r, _k)  or "break")
                entry.bind("<Down>",     lambda e, _r=r:        self._row_focus_down(_r)       or "break")
                entry.bind("<Up>",       lambda e, _r=r:        self._row_focus_up(_r)         or "break")
                entry.bind("<Return>",   lambda e, _r=r:        self._row_enter(_r)            or "break")
                entry.bind("<KeyRelease>", lambda e, _r=r, _k=k: e.char.isdigit() and self._row_focus_right(_r, _k))
                row_entries.append(entry)
            self.row_clue_entries.append(row_entries)

        # Column clue entries — created after rows, so they follow in Tab order.
        self.col_clue_entries = []
        for c in range(self.cols):
            x_mid = self._row_clue_w + c * self._cell_size + self._cell_size // 2
            col_entries: list[tk.Entry] = []
            for k in range(self._max_col_clues):
                y_mid = k * self._cell_size + self._cell_size // 2
                entry = tk.Entry(
                    self.canvas, justify="center",
                    font=self._clue_font, relief="ridge", bg=COLOR_CLUE_BG, width=2,
                )
                self.canvas.create_window(x_mid, y_mid, window=entry, width=ew, height=ew)
                entry.bind("<Down>",     lambda e, _c=c, _k=k: self._col_focus_down(_c, _k) or "break")
                entry.bind("<Up>",       lambda e, _c=c, _k=k: self._col_focus_up(_c, _k)   or "break")
                entry.bind("<Right>",    lambda e, _c=c:        self._col_focus_right(_c)    or "break")
                entry.bind("<Left>",     lambda e, _c=c:        self._col_focus_left(_c)     or "break")
                entry.bind("<Return>",   lambda e, _c=c:        self._col_enter(_c)          or "break")
                entry.bind("<KeyRelease>", lambda e, _c=c, _k=k: e.char.isdigit() and self._col_focus_down(_c, _k))
                col_entries.append(entry)
            self.col_clue_entries.append(col_entries)

        # Wrap Tab from the last column box back to the first row box.
        self.col_clue_entries[-1][-1].bind(
            "<Tab>",
            lambda e: self.row_clue_entries[0][0].focus_set() or "break",
        )

    # -- Keyboard navigation: column entries ----------------------------------

    def _col_focus_down(self, c: int, k: int) -> None:
        """Move focus down within a column; wrap to next column or first row entry."""
        if k + 1 < self._max_col_clues:
            self.col_clue_entries[c][k + 1].focus_set()
        elif c + 1 < self.cols:
            self.col_clue_entries[c + 1][0].focus_set()
        else:
            self.row_clue_entries[0][0].focus_set()

    def _col_focus_up(self, c: int, k: int) -> None:
        """Move focus up within a column; wrap to previous column's last box."""
        if k > 0:
            self.col_clue_entries[c][k - 1].focus_set()
        elif c > 0:
            self.col_clue_entries[c - 1][self._max_col_clues - 1].focus_set()

    def _col_focus_right(self, c: int) -> None:
        """Move focus to the top of the next column."""
        if c + 1 < self.cols:
            self.col_clue_entries[c + 1][0].focus_set()

    def _col_enter(self, c: int) -> None:
        """Enter in a column box: next column, or wrap to the first row clue."""
        if c + 1 < self.cols:
            self.col_clue_entries[c + 1][0].focus_set()
        else:
            self.row_clue_entries[0][0].focus_set()

    def _col_focus_left(self, c: int) -> None:
        """Move focus to the top of the previous column."""
        if c > 0:
            self.col_clue_entries[c - 1][0].focus_set()

    # -- Keyboard navigation: row entries -------------------------------------

    def _row_focus_right(self, r: int, k: int) -> None:
        """Move focus right within a row; wrap to next row or first column entry."""
        if k + 1 < self._max_row_clues:
            self.row_clue_entries[r][k + 1].focus_set()
        elif r + 1 < self.rows:
            self.row_clue_entries[r + 1][0].focus_set()
        else:
            self.col_clue_entries[0][0].focus_set()

    def _row_focus_left(self, r: int, k: int) -> None:
        """Move focus left within a row; wrap to previous row's last box."""
        if k > 0:
            self.row_clue_entries[r][k - 1].focus_set()
        elif r > 0:
            self.row_clue_entries[r - 1][self._max_row_clues - 1].focus_set()

    def _row_focus_down(self, r: int) -> None:
        """Move focus to the start of the next row."""
        if r + 1 < self.rows:
            self.row_clue_entries[r + 1][0].focus_set()

    def _row_enter(self, r: int) -> None:
        """Enter in a row box: next row, or wrap to the first column clue."""
        if r + 1 < self.rows:
            self.row_clue_entries[r + 1][0].focus_set()
        else:
            self.col_clue_entries[0][0].focus_set()

    def _row_focus_up(self, r: int) -> None:
        """Move focus to the start of the previous row."""
        if r > 0:
            self.row_clue_entries[r - 1][0].focus_set()

    # -- Grid interaction -----------------------------------------------------

    def _on_click(self, event: tk.Event) -> None:
        """Cycle the clicked cell: unknown -> black -> white -> unknown."""
        assert self.canvas is not None
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        if cx < self._row_clue_w or cy < self._col_clue_h:
            return

        c = int((cx - self._row_clue_w) // self._cell_size)
        r = int((cy - self._col_clue_h) // self._cell_size)

        if 0 <= r < self.rows and 0 <= c < self.cols:
            new_state = (self.grid_state[r][c] + 1) % 3
            self.grid_state[r][c] = new_state
            self.canvas.itemconfig(self.cell_rects[(r, c)], fill=STATE_COLORS[new_state])

    # -- Solver ---------------------------------------------------------------

    def _collect_clues(self) -> tuple[list[list[int]], list[list[int]]]:
        """Read clue entry widgets and return (row_clues, col_clues).

        Each entry box holds one non-negative integer; zero and blank entries
        are skipped so an empty clue list represents an all-white line.
        """
        def parse_entries(entries: list[tk.Entry]) -> list[int]:
            clue: list[int] = []
            for entry in entries:
                text = entry.get().strip()
                if text:
                    try:
                        n = int(text)
                        if n > 0:
                            clue.append(n)
                    except ValueError:
                        pass
            return clue

        row_clues = [parse_entries(self.row_clue_entries[r]) for r in range(self.rows)]
        col_clues = [parse_entries(self.col_clue_entries[c]) for c in range(self.cols)]
        return row_clues, col_clues

    def _on_solve(self) -> None:
        """Read the current clues and board state, run the solver, show results."""
        assert self._solution_canvas is not None
        assert self._solution_label is not None
        assert self._prev_btn is not None
        assert self._next_btn is not None

        row_clues, col_clues = self._collect_clues()
        log.info(
            "solve requested",
            extra={"rows": self.rows, "cols": self.cols},
        )
        self._solutions = solve(row_clues, col_clues, self.grid_state)
        log.info("solve complete", extra={"solutions": len(self._solutions)})

        if self._solutions:
            self._show_solution(0)
        else:
            self._solution_label.set("No solutions found")
            self._prev_btn.config(state="disabled")
            self._next_btn.config(state="disabled")
            for r in range(self.rows):
                for c in range(self.cols):
                    self._solution_canvas.itemconfig(
                        self._sol_cell_rects[(r, c)], fill=COLOR_BG,
                    )

    def _on_prev_solution(self) -> None:
        """Show the previous solution."""
        if self._solution_idx > 0:
            self._show_solution(self._solution_idx - 1)

    def _on_next_solution(self) -> None:
        """Show the next solution."""
        if self._solution_idx < len(self._solutions) - 1:
            self._show_solution(self._solution_idx + 1)

    def _show_solution(self, idx: int) -> None:
        """Render solutions[idx] on the solution canvas and update nav state."""
        assert self._solution_canvas is not None
        assert self._solution_label is not None
        assert self._prev_btn is not None
        assert self._next_btn is not None

        self._solution_idx = idx
        n = len(self._solutions)
        log.debug("showing solution", extra={"idx": idx + 1, "total": n})
        self._solution_label.set(f"Solution {idx + 1} of {n}")
        self._prev_btn.config(state="normal" if idx > 0 else "disabled")
        self._next_btn.config(state="normal" if idx < n - 1 else "disabled")

        board = self._solutions[idx]
        for r in range(self.rows):
            for c in range(self.cols):
                self._solution_canvas.itemconfig(
                    self._sol_cell_rects[(r, c)],
                    fill=STATE_COLORS[board[r][c]],
                )

    # -- Solution panel -------------------------------------------------------

    def _build_solution_panel(self, parent: tk.Frame) -> None:
        """Build the bottom-half solution display inside parent."""
        sol_total_w = self.cols * self._cell_size + GRID_LINE_W
        sol_total_h = self.rows * self._cell_size + GRID_LINE_W
        log.debug(
            "building solution panel",
            extra={"canvas_w": sol_total_w, "canvas_h": sol_total_h},
        )

        bottom_frame = tk.Frame(parent, bg=COLOR_BG)
        bottom_frame.pack(fill="both", expand=True)

        # Canvas and its right-side nav buttons travel together as a centered unit.
        bot_container = tk.Frame(bottom_frame, bg=COLOR_BG)
        bot_container.pack(anchor="center", pady=(6, 10))

        self._solution_canvas = tk.Canvas(
            bot_container,
            width=sol_total_w,
            height=sol_total_h,
            bg=COLOR_BG,
            highlightthickness=0,
        )
        self._solution_canvas.pack(side="left")

        # Right-side nav: Previous / label / Next centered vertically.
        nav_frame = tk.Frame(bot_container, bg=COLOR_BG)
        nav_frame.pack(side="left", fill="y", padx=(8, 0))

        inner_nav = tk.Frame(nav_frame, bg=COLOR_BG)
        inner_nav.pack(expand=True)  # centers the group vertically within nav_frame

        self._prev_btn = tk.Button(
            inner_nav, text="< Previous", font=("Segoe UI", 9),
            command=self._on_prev_solution, state="disabled", takefocus=False,
        )
        self._prev_btn.pack()

        self._solution_label = tk.StringVar(value="Press Solve to find solutions")
        tk.Label(inner_nav, textvariable=self._solution_label, bg=COLOR_BG,
                 font=("Segoe UI", 9)).pack(pady=4)

        self._next_btn = tk.Button(
            inner_nav, text="Next >", font=("Segoe UI", 9),
            command=self._on_next_solution, state="disabled", takefocus=False,
        )
        self._next_btn.pack()

        self._draw_solution_grid()

    def _draw_solution_grid(self) -> None:
        """Draw an empty solution grid (cells and grid lines, no clue widgets)."""
        assert self._solution_canvas is not None
        self._sol_cell_rects = {}

        count = self.rows * self.cols
        h_lines = self.rows + 1
        v_lines = self.cols + 1
        log.debug(
            "drawing solution grid",
            extra={
                "cells": count,
                "h_lines": h_lines,
                "v_lines": v_lines,
                "total_lines": h_lines + v_lines,
            },
        )

        for r in range(self.rows):
            for c in range(self.cols):
                x0 = c * self._cell_size
                y0 = r * self._cell_size
                rect_id = self._solution_canvas.create_rectangle(
                    x0, y0, x0 + self._cell_size, y0 + self._cell_size,
                    fill=COLOR_BG, outline="",
                )
                self._sol_cell_rects[(r, c)] = rect_id

        x_end = self.cols * self._cell_size
        y_end = self.rows * self._cell_size
        for r in range(self.rows + 1):
            y = r * self._cell_size
            self._solution_canvas.create_line(0, y, x_end, y, fill=COLOR_GRID, width=GRID_LINE_W)
        for c in range(self.cols + 1):
            x = c * self._cell_size
            self._solution_canvas.create_line(x, 0, x, y_end, fill=COLOR_GRID, width=GRID_LINE_W)


def main() -> None:
    """Launch the Nonogram Solver GUI."""
    configure_logging()
    log.info("Nonogram Solver starting")
    root = tk.Tk()
    root.state("zoomed")   # start maximized so window dimensions are known at grid build time
    NonogramApp(root)
    root.mainloop()
    log.info("Nonogram Solver exiting")


if __name__ == "__main__":
    main()
