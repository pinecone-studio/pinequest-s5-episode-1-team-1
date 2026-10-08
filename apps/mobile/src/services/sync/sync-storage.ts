import { File, Paths } from "expo-file-system";

/** This device's sync code and id, kept in a small file so they survive app restarts. */
const FILE_NAME = "bekhi-sync.json";

export interface SavedSync {
  code: string;
  deviceId: string;
}

export function loadSync(): Partial<SavedSync> {
  try {
    const file = new File(Paths.document, FILE_NAME);
    return file.exists ? (JSON.parse(file.textSync()) as Partial<SavedSync>) : {};
  } catch {
    return {};
  }
}

export function saveSync(value: SavedSync): void {
  try {
    new File(Paths.document, FILE_NAME).write(JSON.stringify(value));
  } catch {
    // not saved: a new code is made on the next start
  }
}
