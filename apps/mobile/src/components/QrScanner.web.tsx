/** The computer shows the QR code; only the phone reads one (QrScanner.tsx). */
export function QrScanner(_: { visible: boolean; onCode(code: string): void; onClose(): void }) {
  return null;
}
