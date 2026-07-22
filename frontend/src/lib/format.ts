export function formatDateTime(value?: string | null) {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDate(value?: string | null) {
  if (!value) return "Not set";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDurationUntil(value?: string | null) {
  if (!value) return "No wake-up scheduled";

  const diffMs = new Date(value).getTime() - Date.now();
  if (Number.isNaN(diffMs)) return "Invalid wake-up time";
  if (diffMs <= 0) return "Due now";

  const minutes = Math.round(diffMs / 60000);
  if (minutes < 60) return `${minutes}m`;

  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;

  return `${Math.round(hours / 24)}d`;
}

export function titleize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function compactJson(value: unknown) {
  if (!value || typeof value !== "object") return String(value ?? "");
  return JSON.stringify(value, null, 2);
}
