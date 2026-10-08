import { File, Paths } from "expo-file-system";

/** The BEKHI API address that last answered, so the next start finds the PC at once. */
const FILE_NAME = "bekhi-server.txt";

export function loadServerAddress(): string | null {
  try {
    const file = new File(Paths.document, FILE_NAME);
    return file.exists ? file.textSync().trim() || null : null;
  } catch {
    return null;
  }
}

export function saveServerAddress(base: string): void {
  try {
    new File(Paths.document, FILE_NAME).write(base);
  } catch {
    // not saved: the next start looks for the PC again
  }
}
