/** Dark, Siri-like palette: deep background, glass surfaces, a five-colour glow. */
export const colors = {
  background: "#05060B",
  backgroundTop: "#05060B",
  backgroundBottom: "#0E0A24",
  surface: "rgba(255,255,255,0.07)",
  surfacePressed: "rgba(255,255,255,0.14)",
  border: "rgba(255,255,255,0.12)",
  sheet: "#15161D",
  label: "#FFFFFF",
  secondaryLabel: "rgba(235,235,245,0.62)",
  tertiaryLabel: "rgba(235,235,245,0.36)",
  accent: "#8E9BFF",
  success: "#30D158",
  warning: "#FF9F0A",
  danger: "#FF453A",
} as const;

/** The Siri glow, in order around the orb and the screen edge. */
export const glow = {
  orange: "#FF8A3D",
  pink: "#FF3D9A",
  purple: "#9B5CFF",
  blue: "#3D7BFF",
  cyan: "#3DE2FF",
} as const;

export const radius = { card: 18, chip: 18, sheet: 24 } as const;

/** Content column width on wide screens (the app also runs in a desktop browser). */
export const MAX_CONTENT_WIDTH = 680;
