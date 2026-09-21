// The panes shown in the grid, in display order, until pane sets can be edited.
// Rotating a pane swaps its width and height here, and `maximised` marks the
// one pane that currently fills the grid.
export const PANE_DEFINITIONS = [
	{
		height: 667,
		id: "phone",
		label: "Phone",
		maximised: false,
		width: 375,
	},
	{
		height: 1024,
		id: "tablet",
		label: "Tablet",
		maximised: false,
		width: 768,
	},
	{
		height: 800,
		id: "laptop",
		label: "Laptop",
		maximised: false,
		width: 1280,
	},
	{
		height: 900,
		id: "desktop",
		label: "Desktop",
		maximised: false,
		width: 1440,
	},
];
