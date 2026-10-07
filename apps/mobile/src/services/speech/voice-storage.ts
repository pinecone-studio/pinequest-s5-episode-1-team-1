import { File, Paths } from "expo-file-system";

/** The chosen voice, kept in a small file so it survives app restarts on the phone. */
const FILE_NAME = "duud-voice.txt";

export function loadSavedVoice(): string | null {
  try {
    const file = new File(Paths.document, FILE_NAME);
    return file.exists ? file.textSync().trim() || null : null;
  } catch {
    return null;
  }
}

export function saveVoice(id: string): void {
  try {
    new File(Paths.document, FILE_NAME).write(id);
  } catch {
    // not saved: the choice lasts until the app restarts
  }
}
