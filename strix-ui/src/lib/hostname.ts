/** Pull a hostname out of a typed host or a pasted URL. */
export function hostnameFromInput(raw: string): string {
  const value = raw.trim();
  if (!value) return "";

  const toParse = value.startsWith("//")
    ? `https:${value}`
    : /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(value)
      ? value
      : `https://${value}`;

  try {
    const url = new URL(toParse);
    if (url.username || url.password) return "";
    return url.hostname.replace(/\.$/, "").toLowerCase();
  } catch {
    return value.toLowerCase();
  }
}
