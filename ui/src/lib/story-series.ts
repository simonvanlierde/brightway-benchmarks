/**
 * The series colour (--s1 to --s8) of each solver the stories draw: the one the viewer's charts give
 * its environment label (seriesSlots), so a solver has one colour on the whole site. The labels are
 * the conda-forge charts' the stories link to: "UMFPACK", "PyPardiso, MKL" and "SuperLU".
 * test/story-series.test.ts checks them against the published data; scripts/generate-assets.mjs
 * draws the preview cards with the same slots.
 */
export const SERIES = { umfpack: 3, pypardiso: 7, superlu: 5 } as const;
