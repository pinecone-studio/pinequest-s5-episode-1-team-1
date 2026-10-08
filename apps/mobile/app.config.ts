import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * app.json plus the Google Maps SDK keys for the map tiles, read from apps/mobile/.env (or EAS
 * environment variables) so they stay out of git. Expo Go has its own keys and ignores these.
 */
export default ({ config }: ConfigContext): ExpoConfig => {
  const iosKey = process.env.GOOGLE_MAPS_IOS_API_KEY;
  return {
    ...(config as ExpoConfig),
    plugins: [
      ...(config.plugins ?? []),
      [
        "react-native-maps",
        { androidGoogleMapsApiKey: process.env.GOOGLE_MAPS_ANDROID_API_KEY, iosGoogleMapsApiKey: iosKey },
      ],
    ],
    extra: { ...config.extra, googleMapsOnIos: Boolean(iosKey) },
  };
};
