import { Alert, Platform } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { DOCUMENT_UPLOAD } from "@bekhi/contracts";

/** A contract or official document chosen on this device, to be checked (POST /assistant/document). */
export interface PickedFile {
  uri: string;
  name: string;
  mimeType: string;
  size: number | null;
  /** Web: the browser's own File. */
  file?: File;
}

/** The files, what is wrong with them (in Mongolian), or null when the user cancelled. */
export type Picked = { files: PickedFile[] } | { problem: string } | null;

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const ACCEPTED: readonly string[] = DOCUMENT_UPLOAD.mime_types;
const BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: DOCX,
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
  heif: "image/heif",
};
/** Phone cameras give 3-6 MB pictures; this keeps ten pages under the upload limit and still readable. */
const PHOTO_QUALITY = 0.6;

const extension = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

/** Phones and browsers often send Word files as application/octet-stream: the name says what it is. */
function mimeOf(name: string, given: string | null | undefined): string {
  if (given && ACCEPTED.includes(given)) return given;
  return BY_EXTENSION[extension(name)] ?? given ?? "";
}

function checked(files: PickedFile[]): Picked {
  if (files.length === 0) return null;
  if (files.some((f) => extension(f.name) === "doc")) {
    return { problem: "Хуучин .doc файлыг шалгаж чадахгүй. Word дээр .docx болгож хадгалаад дахин оролдоорой." };
  }
  if (files.some((f) => !ACCEPTED.includes(f.mimeType))) {
    return { problem: "PDF, Word (.docx) файл эсвэл баримтын зураг л шалгана." };
  }
  if (files.length > 1 && files.some((f) => !f.mimeType.startsWith("image/"))) {
    return { problem: "Нэг удаад нэг PDF эсвэл Word файл, эсвэл нэг баримтын хуудсуудын зургийг шалгана." };
  }
  if (files.length > DOCUMENT_UPLOAD.max_files) {
    return { problem: `Нэг удаад ${DOCUMENT_UPLOAD.max_files} хүртэл хуудасны зураг шалгана.` };
  }
  const total = files.reduce((sum, f) => sum + (f.size ?? 0), 0);
  if (total > DOCUMENT_UPLOAD.max_total_bytes) {
    return { problem: `Файл хэт том байна. ${DOCUMENT_UPLOAD.max_total_bytes / 1_000_000} MB хүртэлхийг шалгана.` };
  }
  return { files };
}

async function pickFiles(): Promise<Picked> {
  const res = await DocumentPicker.getDocumentAsync({
    type: [...ACCEPTED],
    multiple: true,
    copyToCacheDirectory: true,
    base64: false,
  });
  if (res.canceled) return null;
  return checked(
    res.assets.map((a) => ({ uri: a.uri, name: a.name, mimeType: mimeOf(a.name, a.mimeType), size: a.size ?? null, file: a.file })),
  );
}

function fromImage(a: ImagePicker.ImagePickerAsset, page: number): PickedFile {
  const name = a.fileName || `huudas-${page}.jpg`;
  return { uri: a.uri, name, mimeType: mimeOf(name, a.mimeType ?? "image/jpeg"), size: a.fileSize ?? null, file: a.file };
}

/** iPhone: pages photographed earlier are in Photos, which the file picker does not show. */
async function pickPhotos(): Promise<Picked> {
  const res = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ["images"],
    allowsMultipleSelection: true,
    selectionLimit: DOCUMENT_UPLOAD.max_files,
    quality: PHOTO_QUALITY,
  });
  if (res.canceled) return null;
  return checked(res.assets.map((a, i) => fromImage(a, i + 1)));
}

const ask = (title: string, yes: string, no: string) =>
  new Promise<boolean>((resolve) =>
    Alert.alert(title, undefined, [
      { text: no, style: "cancel", onPress: () => resolve(false) },
      { text: yes, onPress: () => resolve(true) },
    ], { cancelable: false }),
  );

/** Photograph the pages one by one, then check them together. */
async function takePhotos(): Promise<Picked> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) return { problem: "Камерын зөвшөөрөл хэрэгтэй байна. Утасны тохиргооноос зөвшөөрнө үү." };
  const pages: PickedFile[] = [];
  for (;;) {
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: PHOTO_QUALITY });
    const asset = shot.canceled ? undefined : shot.assets[0];
    if (!asset) break;
    pages.push(fromImage(asset, pages.length + 1));
    if (pages.length >= DOCUMENT_UPLOAD.max_files) break;
    if (!(await ask(`${pages.length} хуудас авлаа. Дараагийн хуудсыг авах уу?`, "Дараагийн хуудас", "Шалгах"))) break;
  }
  return checked(pages);
}

/**
 * The document to check: a PDF or Word file, or photos of its pages. The computer opens its file
 * picker straight away; the phone asks how first.
 */
export function chooseDocument(): Promise<Picked> {
  if (Platform.OS === "web") return pickFiles();
  return new Promise((resolve) => {
    const run = (pick: () => Promise<Picked>) => () =>
      void pick().then(resolve, (e: unknown) => {
        console.warn("document pick failed", e);
        resolve({ problem: "Файл нээж чадсангүй. Дахин оролдоно уу." });
      });
    Alert.alert(
      "Баримт шалгуулах",
      "Гэрээ, албан бичгийг гарын үсэг зурахаас өмнө шалгая.",
      [
        { text: "Файл (PDF, Word)", onPress: run(pickFiles) },
        // Android shows three buttons at most; its file picker already offers the gallery.
        ...(Platform.OS === "ios" ? [{ text: "Зургийн сангаас", onPress: run(pickPhotos) }] : []),
        { text: "Зураг авах", onPress: run(takePhotos) },
        { text: "Болих", style: "cancel" as const, onPress: () => resolve(null) },
      ],
      { cancelable: true, onDismiss: () => resolve(null) },
    );
  });
}
