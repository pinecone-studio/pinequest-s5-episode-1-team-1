import type { PickedFile } from "./pick";

/** Web: the picker gives the browser's File; its type is often empty for Word files, so it is set here. */
export async function appendDocuments(form: FormData, files: PickedFile[]): Promise<void> {
  for (const f of files) {
    const data = f.file ?? (await (await fetch(f.uri)).blob());
    form.append("files", new Blob([data], { type: f.mimeType }), f.name);
  }
}
