#!/usr/bin/env python3
"""Nonogram solver -- GUI for grid input and visualisation."""

from __future__ import annotations
import math
import tkinter as tk
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

# -- Layout -------------------------------------------------------------------
CELL_SIZE     = 57   # px per grid square
CLUE_BOX_SIZE = 40   # px per individual clue number box (both axes)
GRID_LINE_W   = 4    # px thickness of grid lines
CLUE_FONT     = ("Consolas", 12)


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

        self._show_setup()

    # -- Setup screen ---------------------------------------------------------

    def _show_setup(self) -> None:
        """Display the grid-size input form."""
        if self._current_frame is not None:
            self._current_frame.destroy()
        self.canvas = None
        self._solution_canvas = None

        frame = tk.Frame(self.root, padx=40, pady=40, bg=COLOR_BG)
        frame.pack(fill="both", expand=True)
        self._current_frame = frame

        tk.Label(
            frame, text="Nonogram Solver",
            font=("Segoe UI", 18, "bold"), bg=COLOR_BG,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 24))

        tk.Label(frame, text="Rows:", bg=COLOR_BG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="e", padx=8)
        self._rows_var = tk.StringVar(value="5")
        rows_entry = tk.Entry(frame, textvariable=self._rows_var, width=6,
                              font=("Segoe UI", 10))
        rows_entry.grid(row=1, column=1, sticky="w")

        tk.Label(frame, text="Columns:", bg=COLOR_BG,
                 font=("Segoe UI", 10)).grid(row=2, column=0, sticky="e", padx=8, pady=8)
        self._cols_var = tk.StringVar(value="5")
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

        self.root.unbind("<Return>")
        self.rows = rows
        self.cols = cols
        self.grid_state = [[0] * cols for _ in range(rows)]
        self._build_grid_ui()

    # -- Grid screen ----------------------------------------------------------

    def _build_grid_ui(self) -> None:
        """Build the interactive nonogram grid (top half) and solution panel (bottom half)."""
        if self._current_frame is not None:
            self._current_frame.destroy()

        # Clue area sizes depend on grid dimensions
        self._max_row_clues = math.ceil(self.cols / 2)
        self._max_col_clues = math.ceil(self.rows / 2)
        self._row_clue_w = self._max_row_clues * CLUE_BOX_SIZE
        self._col_clue_h = self._max_col_clues * CLUE_BOX_SIZE

        outer = tk.Frame(self.root, bg=COLOR_BG)
        outer.pack(fill="both", expand=True)
        self._current_frame = outer

        # ---- Top half: input grid -------------------------------------------
        top_frame = tk.Frame(outer, bg=COLOR_BG)
        top_frame.pack(fill="both", expand=True)

        toolbar = tk.Frame(top_frame, bg=COLOR_BG, pady=6)
        toolbar.pack(fill="x", padx=10)
        tk.Button(toolbar, text="New Grid", command=self._show_setup,
                  font=("Segoe UI", 9)).pack(side="left")
        tk.Button(toolbar, text="Solve", command=self._on_solve,
                  font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))

        total_w = self._row_clue_w + self.cols * CELL_SIZE + GRID_LINE_W
        total_h = self._col_clue_h + self.rows * CELL_SIZE + GRID_LINE_W

        container = tk.Frame(top_frame, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        h_scroll = tk.Scrollbar(container, orient="horizontal")
        v_scroll = tk.Scrollbar(container, orient="vertical")
        h_scroll.pack(side="bottom", fill="x")
        v_scroll.pack(side="right", fill="y")

        self.canvas = tk.Canvas(
            container,
            width=min(total_w, 960),
            height=min(total_h, 500),
            scrollregion=(0, 0, total_w, total_h),
            xscrollcommand=h_scroll.set,
            yscrollcommand=v_scroll.set,
            bg=COLOR_BG,
            highlightthickness=0,
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        h_scroll.config(command=self.canvas.xview)
        v_scroll.config(command=self.canvas.yview)

        self._draw_cells()
        self._draw_grid_lines()
        self._create_clue_widgets()

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel_v)
        self.canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_h)

        # ---- Divider --------------------------------------------------------
        tk.Frame(outer, height=3, bg=COLOR_GRID).pack(fill="x")

        # ---- Bottom half: solution display ----------------------------------
        self._solutions = []
        self._solution_idx = 0
        self._build_solution_panel(outer)

    def _draw_cells(self) -> None:
        """Draw all grid cells as filled rectangles without outlines."""
        assert self.canvas is not None
        self.cell_rects = {}
        for r in range(self.rows):
            for c in range(self.cols):
                x0 = self._row_clue_w + c * CELL_SIZE
                y0 = self._col_clue_h + r * CELL_SIZE
                rect_id = self.canvas.create_rectangle(
                    x0, y0,
                    x0 + CELL_SIZE, y0 + CELL_SIZE,
                    fill=COLOR_UNKNOWN,
                    outline="",
                )
                self.cell_rects[(r, c)] = rect_id

    def _draw_grid_lines(self) -> None:
        """Draw 4px grid lines over the cell area and clue-area separators."""
        assert self.canvas is not None
        gx = self._row_clue_w
        gy = self._col_clue_h
        x_end = gx + self.cols * CELL_SIZE
        y_end = gy + self.rows * CELL_SIZE

        for r in range(self.rows + 1):
            y = gy + r * CELL_SIZE
            self.canvas.create_line(gx, y, x_end, y, fill=COLOR_GRID, width=GRID_LINE_W)

        for c in range(self.cols + 1):
            x = gx + c * CELL_SIZE
            self.canvas.create_line(x, gy, x, y_end, fill=COLOR_GRID, width=GRID_LINE_W)

        # Separator lines that extend through the clue areas
        self.canvas.create_line(gx, 0, gx, y_end, fill=COLOR_GRID, width=GRID_LINE_W)
        self.canvas.create_line(0, gy, x_end, gy, fill=COLOR_GRID, width=GRID_LINE_W)

    def _create_clue_widgets(self) -> None:
        """Embed Entry widgets for row and column clues with keyboard navigation.

        Row clues: ceil(cols/2) boxes per row, arranged left-to-right.
        Column clues: ceil(rows/2) boxes per column, arranged top-to-bottom.
        Down navigates through column clue boxes; Right navigates through row clue boxes.
        """
        assert self.canvas is not None
        ew = CLUE_BOX_SIZE - 6   # entry display size in pixels

        # Row clue entries
        self.row_clue_entries = []
        for r in range(self.rows):
            y_mid = self._col_clue_h + r * CELL_SIZE + CELL_SIZE // 2
            row_entries: list[tk.Entry] = []
            for k in range(self._max_row_clues):
                x_mid = k * CLUE_BOX_SIZE + CLUE_BOX_SIZE // 2
                entry = tk.Entry(
                    self.canvas, justify="center",
                    font=CLUE_FONT, relief="ridge", bg=COLOR_CLUE_BG, width=2,
                )
                self.canvas.create_window(x_mid, y_mid, window=entry, width=ew, height=ew)
                entry.bind(
                    "<Right>",
                    lambda e, _r=r, _k=k: self._row_focus_right(_r, _k) or "break",
                )
                row_entries.append(entry)
            self.row_clue_entries.append(row_entries)

        # Column clue entries
        self.col_clue_entries = []
        for c in range(self.cols):
            x_mid = self._row_clue_w + c * CELL_SIZE + CELL_SIZE // 2
            col_entries: list[tk.Entry] = []
            for k in range(self._max_col_clues):
                y_mid = k * CLUE_BOX_SIZE + CLUE_BOX_SIZE // 2
                entry = tk.Entry(
                    self.canvas, justify="center",
                    font=CLUE_FONT, relief="ridge", bg=COLOR_CLUE_BG, width=2,
                )
                self.canvas.create_window(x_mid, y_mid, window=entry, width=ew, height=ew)
                entry.bind(
                    "<Down>",
                    lambda e, _c=c, _k=k: self._col_focus_down(_c, _k) or "break",
                )
                col_entries.append(entry)
            self.col_clue_entries.append(col_entries)

    # -- Keyboard navigation --------------------------------------------------

    def _col_focus_down(self, c: int, k: int) -> None:
        """Move focus down from column clue entry (c, k).

        Wraps to the next column at the bottom, then to the first row entry
        after the last column's last box.
        """
        if k + 1 < self._max_col_clues:
            self.col_clue_entries[c][k + 1].focus_set()
        elif c + 1 < self.cols:
            self.col_clue_entries[c + 1][0].focus_set()
        else:
            self.row_clue_entries[0][0].focus_set()

    def _row_focus_right(self, r: int, k: int) -> None:
        """Move focus right from row clue entry (r, k).

        Wraps to the next row at the right edge, then to the first column
        entry after the last row's last box.
        """
        if k + 1 < self._max_row_clues:
            self.row_clue_entries[r][k + 1].focus_set()
        elif r + 1 < self.rows:
            self.row_clue_entries[r + 1][0].focus_set()
        else:
            self.col_clue_entries[0][0].focus_set()

    # -- Grid interaction -----------------------------------------------------

    def _on_click(self, event: tk.Event) -> None:
        """Cycle the clicked cell: unknown -> black -> white -> unknown."""
        assert self.canvas is not None
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        if cx < self._row_clue_w or cy < self._col_clue_h:
            return

        c = int((cx - self._row_clue_w) // CELL_SIZE)
        r = int((cy - self._col_clue_h) // CELL_SIZE)

        if 0 <= r < self.rows and 0 <= c < self.cols:
            new_state = (self.grid_state[r][c] + 1) % 3
            self.grid_state[r][c] = new_state
            self.canvas.itemconfig(self.cell_rects[(r, c)], fill=STATE_COLORS[new_state])

    def _on_mousewheel_v(self, event: tk.Event) -> None:
        """Scroll the canvas vertically."""
        assert self.canvas is not None
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_h(self, event: tk.Event) -> None:
        """Scroll the canvas horizontally."""
        assert self.canvas is not None
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

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
        self._solutions = solve(row_clues, col_clues, self.grid_state)

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
        bottom_frame = tk.Frame(parent, bg=COLOR_BG)
        bottom_frame.pack(fill="both", expand=True)

        # Navigation bar
        nav = tk.Frame(bottom_frame, bg=COLOR_BG, pady=6)
        nav.pack(fill="x", padx=10)

        self._prev_btn = tk.Button(
            nav, text="< Previous", font=("Segoe UI", 9),
            command=self._on_prev_solution, state="disabled",
        )
        self._prev_btn.pack(side="left")

        self._solution_label = tk.StringVar(value="Press Solve to find solutions")
        tk.Label(nav, textvariable=self._solution_label, bg=COLOR_BG,
                 font=("Segoe UI", 9)).pack(side="left", padx=12)

        self._next_btn = tk.Button(
            nav, text="Next >", font=("Segoe UI", 9),
            command=self._on_next_solution, state="disabled",
        )
        self._next_btn.pack(side="left")

        # Solution canvas (no clue area — pure grid)
        sol_total_w = self.cols * CELL_SIZE + GRID_LINE_W
        sol_total_h = self.rows * CELL_SIZE + GRID_LINE_W

        sol_container = tk.Frame(bottom_frame, bg=COLOR_BG)
        sol_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        sol_h_scroll = tk.Scrollbar(sol_container, orient="horizontal")
        sol_v_scroll = tk.Scrollbar(sol_container, orient="vertical")
        sol_h_scroll.pack(side="bottom", fill="x")
        sol_v_scroll.pack(side="right", fill="y")

        self._solution_canvas = tk.Canvas(
            sol_container,
            width=min(sol_total_w, 960),
            height=min(sol_total_h, 500),
            scrollregion=(0, 0, sol_total_w, sol_total_h),
            xscrollcommand=sol_h_scroll.set,
            yscrollcommand=sol_v_scroll.set,
            bg=COLOR_BG,
            highlightthickness=0,
        )
        self._solution_canvas.pack(side="left", fill="both", expand=True)
        sol_h_scroll.config(command=self._solution_canvas.xview)
        sol_v_scroll.config(command=self._solution_canvas.yview)

        self._solution_canvas.bind("<MouseWheel>", self._on_sol_mousewheel_v)
        self._solution_canvas.bind("<Shift-MouseWheel>", self._on_sol_mousewheel_h)

        self._draw_solution_grid()

    def _draw_solution_grid(self) -> None:
        """Draw an empty solution grid (cells and grid lines, no clue widgets)."""
        assert self._solution_canvas is not None
        self._sol_cell_rects = {}

        for r in range(self.rows):
            for c in range(self.cols):
                x0 = c * CELL_SIZE
                y0 = r * CELL_SIZE
                rect_id = self._solution_canvas.create_rectangle(
                    x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE,
                    fill=COLOR_BG, outline="",
                )
                self._sol_cell_rects[(r, c)] = rect_id

        x_end = self.cols * CELL_SIZE
        y_end = self.rows * CELL_SIZE
        for r in range(self.rows + 1):
            y = r * CELL_SIZE
            self._solution_canvas.create_line(0, y, x_end, y, fill=COLOR_GRID, width=GRID_LINE_W)
        for c in range(self.cols + 1):
            x = c * CELL_SIZE
            self._solution_canvas.create_line(x, 0, x, y_end, fill=COLOR_GRID, width=GRID_LINE_W)

    def _on_sol_mousewheel_v(self, event: tk.Event) -> None:
        """Scroll the solution canvas vertically."""
        assert self._solution_canvas is not None
        self._solution_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_sol_mousewheel_h(self, event: tk.Event) -> None:
        """Scroll the solution canvas horizontally."""
        assert self._solution_canvas is not None
        self._solution_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")


def main() -> None:
    """Launch the Nonogram Solver GUI."""
    root = tk.Tk()
    NonogramApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
