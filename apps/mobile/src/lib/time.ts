const pad = (n: number) => String(n).padStart(2, "0");

/** Device-local ISO-8601 with offset, e.g. "2026-10-07T09:00:00+08:00". */
export function toLocalIso(date: Date): string {
  const offsetMin = -date.getTimezoneOffset();
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

export function localDate(date: Date): string {
  return toLocalIso(date).slice(0, 10);
}

export function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Ulaanbaatar";
  } catch {
    return "Asia/Ulaanbaatar";
  }
}

/** Tomorrow at hh:mm in device-local time. */
export function tomorrowAt(hours: number, minutes = 0, now = new Date()): Date {
  const d = new Date(now);
  d.setDate(d.getDate() + 1);
  d.setHours(hours, minutes, 0, 0);
  return d;
}

/**
 * Conversational Mongolian for a time, read from the ISO string as written (it is
 * already in the user's offset): "маргааш өглөө 9 цагт", "өнөөдөр орой 7:30-д".
 */
export function formatWhenMn(iso: string, nowIso: string): string {
  const date = iso.slice(0, 10);
  const h = Number(iso.slice(11, 13));
  const m = Number(iso.slice(14, 16));
  const dayDiff = Math.round((Date.parse(date) - Date.parse(nowIso.slice(0, 10))) / 86_400_000);

  const day =
    dayDiff === 0
      ? "өнөөдөр"
      : dayDiff === 1
        ? "маргааш"
        : dayDiff === 2
          ? "нөгөөдөр"
          : `${Number(date.slice(5, 7))} сарын ${Number(date.slice(8, 10))}-нд`;
  const part = h < 5 ? "шөнө" : h < 12 ? "өглөө" : h < 18 ? "өдөр" : h < 23 ? "орой" : "шөнө";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  const clock = m === 0 ? `${h12} цагт` : `${h12}:${pad(m)}-д`;
  return `${day} ${part} ${clock}`;
}
