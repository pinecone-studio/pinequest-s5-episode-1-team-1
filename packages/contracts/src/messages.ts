/**
 * Fixed Mongolian copy used by both backend and app. Conversational, not formal.
 */
export const MN = {
  ui: {
    greeting: "Сайн байна уу 👋",
    idle: "Ярина уу...",
    listening: "Сонсож байна...",
    processing: "Ойлгож байна...",
    executing: "Үйлдлийг хийж байна...",
    success: "За, хийчихлээ.",
    error: "Уучлаарай, дахин хэлээд өгөөч.",
    confirmYes: "Тийм",
    confirmNo: "Үгүй",
  },
  errors: {
    stt: "Уучлаарай, сайн сонсогдсонгүй. Дахин хэлээд өгөөч.",
    llm: "Уучлаарай, одоогоор ойлгоход асуудал гарлаа.",
    iosUnavailable: "Уучлаарай, утсан дээр энэ үйлдлийг одоохондоо хийж чадахгүй байна.",
    permissionDenied: "Энэ үйлдлийг хийхийн тулд утасныхаа тохиргооноос зөвшөөрөл өгөх хэрэгтэй байна.",
  },
} as const;

/** On-device clarification when several contacts match. Names never leave the phone. */
export function contactAmbiguityQuestion(name: string, count: number, verb: "call" | "message"): string {
  const action = verb === "call" ? "залгах" : "бичих";
  return `${name} гэсэн ${count} контакт байна. Аль руу нь ${action} вэ?`;
}

export function contactNotFound(name: string): string {
  return `${name} гэсэн контакт олдсонгүй.`;
}
