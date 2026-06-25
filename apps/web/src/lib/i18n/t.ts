// Minimal Korean-only message lookup. `messages.ts` is the single source of
// truth for all UI copy; `t(key)` returns the Korean string and interpolates
// any `{placeholder}` tokens from `params`. No library, no runtime locale
// switch — the app renders Korean. Data (satellite names, NORAD IDs, audit row
// values, etc.) never passes through here; it stays as the backend provides it.

import { messages } from "./messages";

export type MessageKey = keyof typeof messages;

export function t(
  key: MessageKey,
  params?: Record<string, string | number>
): string {
  let out: string = messages[key];
  if (params) {
    for (const [token, value] of Object.entries(params)) {
      // split/join instead of replaceAll — no String.prototype.replaceAll lib
      // dependency, and it replaces every occurrence of the token.
      out = out.split(`{${token}}`).join(String(value));
    }
  }
  return out;
}
