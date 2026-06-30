// VIOLATION (coder.presentation.i18n-config): the supported-locale list is a
// hardcoded array with no reference to the shared manifest.
export const locales = ["en", "fr", "de"];

export const i18nConfig = {
  supportedLocales: locales,
  fallback: "en",
};
