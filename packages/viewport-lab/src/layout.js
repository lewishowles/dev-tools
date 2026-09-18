// The height of the name and size strip above each pane.
export const PANE_LABEL_HEIGHT = 40;
// The space between neighbouring panes.
export const GRID_GAP = 64;
// The space between the panes and the edges of the grid.
export const GRID_PADDING = 64;

/**
 * Calculate the cell positions and scrollable size for the pane grid.
 *
 * @param  {object[]}  panes
 *     Pane definitions to place in source order.
 * @param  {number}  viewportWidth
 *     Window content width used to wrap panes into rows.
 * @returns {{cells: object[], contentHeight: number, contentWidth: number}}
 *     Grid cells and the full size required by the renderer page.
 */
export function createGridLayout(panes, viewportWidth) {
	const availableWidth = Math.max(viewportWidth - GRID_PADDING * 2, 1);
	const cells = [];

	let contentWidth = 0;
	let rowHeight = 0;
	let rowWidth = 0;
	let rowTop = GRID_PADDING;
	let cellLeft = GRID_PADDING;

	for (const pane of panes) {
		const paneCellHeight = PANE_LABEL_HEIGHT + pane.height;

		if (rowWidth > 0 && rowWidth + GRID_GAP + pane.width > availableWidth) {
			rowTop += rowHeight + GRID_GAP;
			cellLeft = GRID_PADDING;
			rowHeight = 0;
			rowWidth = 0;
		}

		const nextRowWidth = rowWidth === 0 ? pane.width : rowWidth + GRID_GAP + pane.width;

		cells.push({
			height: pane.height,
			id: pane.id,
			label: pane.label,
			left: cellLeft,
			top: rowTop,
			width: pane.width,
		});

		rowWidth = nextRowWidth;
		cellLeft = GRID_PADDING + rowWidth + GRID_GAP;
		rowHeight = Math.max(rowHeight, paneCellHeight);
		contentWidth = Math.max(contentWidth, rowWidth);
	}

	return {
		cells,
		contentHeight: rowTop + rowHeight + GRID_PADDING,
		contentWidth: contentWidth + GRID_PADDING * 2,
	};
}
