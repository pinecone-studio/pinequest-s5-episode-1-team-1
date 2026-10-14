import { File } from "expo-file-system";
import type { PickedFile } from "./pick";

/** Native: Expo's fetch reads any form part that has a `bytes()` method (see audio-upload.ts). */
export async function appendDocuments(form: FormData, files: PickedFile[]): Promise<void> {
  for (const f of files) {
    const file = new File(f.uri);
    form.append("files", { name: f.name, type: f.mimeType, bytes: () => file.bytes() } as unknown as Blob);
  }
}
