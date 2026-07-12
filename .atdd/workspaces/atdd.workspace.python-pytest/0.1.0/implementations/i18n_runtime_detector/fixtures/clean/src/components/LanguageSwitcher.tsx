// GREEN: the switcher sources its locale list from the shared SUPPORTED_LOCALES,
// imported from the i18n config — no hardcoded array.
import { SUPPORTED_LOCALES } from "../i18nConfig";

export function LanguageSwitcher() {
  return SUPPORTED_LOCALES.map((l) => l);
}
