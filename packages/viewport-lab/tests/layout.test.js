import { GRID_GAP, GRID_PADDING, PANE_LABEL_HEIGHT, createGridLayout } from "../src/layout.js";
import { expect, test } from "bun:test";

test("wraps panes into rows when their true widths do not fit", () => {
	const panes = [
		{ height: 667, id: "phone", label: "Phone", width: 375 },
		{ height: 1024, id: "tablet", label: "Tablet", width: 768 },
	];

	const layout = createGridLayout(panes, 800);

	expect(layout.cells).toEqual([
		{
			height: 667,
			id: "phone",
			label: "Phone",
			left: GRID_PADDING,
			top: GRID_PADDING,
			width: 375,
		},
		{
			height: 1024,
			id: "tablet",
			label: "Tablet",
			left: GRID_PADDING,
			top: GRID_PADDING + 667 + PANE_LABEL_HEIGHT + GRID_GAP,
			width: 768,
		},
	]);

	expect(layout.contentWidth).toBe(896);
	expect(layout.contentHeight).toBe(1963);
});

test("places panes side by side when their true widths fit", () => {
	const panes = [
		{ height: 400, id: "first", label: "First", width: 320 },
		{ height: 500, id: "second", label: "Second", width: 480 },
	];

	const layout = createGridLayout(panes, 1000);

	expect(layout.cells[1].left).toBe(GRID_PADDING + panes[0].width + GRID_GAP);
	expect(layout.contentWidth).toBe(GRID_PADDING * 2 + panes[0].width + GRID_GAP + panes[1].width);
});
