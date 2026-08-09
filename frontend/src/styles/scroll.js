// =============================================================================
// frontend/src/styles/scroll.js
// Shared layout primitives so every page scrolls consistently.
//
// The rule that matters: a flex child defaults to min-height:auto and refuses
// to shrink below its content, which silently disables overflow:auto. Every
// scroll container below therefore sets minHeight/minWidth to 0.
// =============================================================================

/** Full-viewport page that never scrolls itself — its children do. */
export const pageShell = {
  height: "100vh", minHeight: 0,
  display: "flex", flexDirection: "column",
  overflow: "hidden",
  background: "#050c1a", color: "#e2e8f0",
  fontFamily: "'IBM Plex Mono','Fira Code',monospace",
};

/** Fixed bar at the top or bottom of a pageShell. */
export const bar = {
  flexShrink: 0, flexWrap: "wrap",
  display: "flex", alignItems: "center",
};

/** The single scrolling body of a page. */
export const scrollBody = {
  flex: 1, minHeight: 0,
  overflowY: "auto", overflowX: "auto",
};

/** A vertically scrolling column (sidebars). */
export const scrollColumn = {
  flex: 1, minHeight: 0,
  overflowY: "auto", overflowX: "hidden",
};

/** A table or list that scrolls inside a card, leaving room for page chrome. */
export const scrollCard = (reserve = 300) => ({
  overflow: "auto",
  maxHeight: `calc(100vh - ${reserve}px)`,
});

/** Header row that stays visible while a scrollCard scrolls. */
export const stickyHeader = { position: "sticky", top: 0, zIndex: 2 };
