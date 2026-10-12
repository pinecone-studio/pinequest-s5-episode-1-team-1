import { StyleSheet } from "react-native";
import { colors } from "@/theme";

/** Shared look of the Settings sheet's sections (Settings.tsx, LinkSection.tsx). */
export const settingStyles = StyleSheet.create({
  section: { fontSize: 13, fontWeight: "600", color: colors.secondaryLabel, marginTop: 20, marginBottom: 8, marginLeft: 4 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: 14,
  },
  rowTitle: { fontSize: 16, color: colors.label },
  body: { fontSize: 14, lineHeight: 20, color: colors.secondaryLabel },
  hint: { fontSize: 12, lineHeight: 17, color: colors.tertiaryLabel },
});
