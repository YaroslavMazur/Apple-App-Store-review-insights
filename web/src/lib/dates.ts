// Treat tz-less ISO strings as UTC so naive timestamps from older DB rows
// don't get parsed in the browser's local timezone.
export function parseServerDate(iso: string): Date {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTz ? iso : `${iso}Z`);
}

export function relativeAgo(iso: string): string {
  const ms = Date.now() - parseServerDate(iso).getTime();
  const minutes = Math.round(ms / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function formatServerDate(iso: string): string {
  return parseServerDate(iso).toLocaleString();
}
