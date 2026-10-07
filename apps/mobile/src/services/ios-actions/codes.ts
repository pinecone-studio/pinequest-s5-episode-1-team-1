/** Why a device action could not run here (kept apart so the assistant layer can import it without a cycle). */
export const NATIVE_UNAVAILABLE = {
  web: "WEB_NO_IPHONE_ACTIONS",
  expoGo: "EXPO_GO_NATIVE_UNAVAILABLE",
  notBuilt: "NATIVE_MODULE_NOT_BUILT",
} as const;
