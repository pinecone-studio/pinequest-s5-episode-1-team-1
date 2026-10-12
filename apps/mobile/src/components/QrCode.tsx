import { useMemo } from "react";
import { create } from "qrcode";
import Svg, { Path, Rect } from "react-native-svg";

const QUIET_ZONE = 4; // modules of white around the code, which scanners need

/** `value` as a QR code: dark on white with a quiet zone, so any phone camera reads it from a screen. */
export function QrCode({ value, size }: { value: string; size: number }) {
  const { path, extent } = useMemo(() => {
    const { modules } = create(value, { errorCorrectionLevel: "M" });
    let d = "";
    for (let y = 0; y < modules.size; y++) {
      for (let x = 0; x < modules.size; x++) {
        if (modules.get(y, x)) d += `M${x + QUIET_ZONE} ${y + QUIET_ZONE}h1v1h-1z`;
      }
    }
    return { path: d, extent: modules.size + 2 * QUIET_ZONE };
  }, [value]);

  return (
    <Svg width={size} height={size} viewBox={`0 0 ${extent} ${extent}`} accessibilityLabel="Холбох QR код">
      <Rect width={extent} height={extent} rx={2} fill="#FFFFFF" />
      <Path d={path} fill="#05060B" />
    </Svg>
  );
}
