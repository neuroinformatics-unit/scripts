import sys

from brainglobe_utils.cells.cells import match_cells
from brainglobe_utils.IO.cells import get_cells, save_cells
from pathlib import Path

if __name__ == "__main__":
    pr_number = Path(sys.argv[1])
    working_dir = Path.home() / f".cellfinder_comparison_{pr_number}"
    cells_main_path = working_dir / "cellfinder_main" / "points" / "cell_classification.xml"
    cells_pr_path = working_dir / f"cellfinder_{pr_number}" / "points" / "cell_classification.xml"

    cells_main = get_cells(str(cells_main_path))
    cells_pr = get_cells(str(cells_pr_path))

    only_main, matched_cells, only_vis = match_cells(cells_main, cells_pr, threshold=0.1)


    print(f"Number of cells only found with cellfinder from main: {len(only_main)}")
    print(f"Number of cells only found with cellfinder from {pr_number}: {len(only_vis)}")
    print(f"Number of matched cells: {len(matched_cells)}")
    print(f"Matching proportion: {float(len(matched_cells)) / max(len(cells_main), len(cells_pr))}")

    only_main_cells = []
    for cell_index in only_main:
        only_main_cells.append(cells_main[cell_index])

    only_vis_cells = []
    for cell_index in only_vis:
        only_vis_cells.append(cells_pr[cell_index])

    if len(only_main_cells) != 0:
        save_cells(only_main_cells, str(working_dir / "only_main.xml"))
    if len(only_vis_cells) != 0:
        save_cells(only_vis_cells, str(working_dir / "only_vis.xml"))
