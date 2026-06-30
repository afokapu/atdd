// GREEN: supported locales are derived from the shared manifest, not hardcoded.
import { SUPPORTED_LOCALES } from "./localeManifest";

export const i18nConfig = {
  supportedLocales: SUPPORTED_LOCALES,
  fallback: "en",
};
