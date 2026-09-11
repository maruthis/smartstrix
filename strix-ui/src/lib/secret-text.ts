const SECRET_PATTERNS: RegExp[] = [
  /\bauthorization\s*:\s*\S+(?:\s+\S+)*/i,
  /\bbearer\s+[A-Za-z0-9\-._~+/]+=*/i,
  /\b(cookie|set-cookie)\s*:\s*\S+/i,
  /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/,
  /\bglpat-[A-Za-z0-9_\-]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
  /\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password|passwd|private[_-]?key)\s*[:=]\s*\S+/i,
];

export function containsSecretShapedText(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => pattern.test(value));
}
