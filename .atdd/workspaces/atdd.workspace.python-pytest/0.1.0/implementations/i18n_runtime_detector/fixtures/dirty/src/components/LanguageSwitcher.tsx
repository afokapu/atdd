// VIOLATION (coder.presentation.i18n-switcher): the options list is a hardcoded
// locale array instead of reading the shared list. (Comment deliberately avoids
// the allow-listed tokens so it does not self-absolve the detection.)
import { useState } from "react";

const options = [
  { locale: "en", label: "English" },
  { locale: "fr", label: "Francais" },
];

export function LanguageSwitcher() {
  const [current, setCurrent] = useState(options[0]);
  return current.locale;
}
