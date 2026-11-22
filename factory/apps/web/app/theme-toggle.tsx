"use client";

import { useEffect, useState } from "react";
import { THEME_STORAGE_KEY } from "@/lib/theme";

type Theme = "system" | "light" | "dark";

const ORDER: Theme[] = ["system", "light", "dark"];
const LABEL: Record<Theme, string> = { system: "◐ Sistema", light: "☀ Claro", dark: "☾ Oscuro" };

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    delete root.dataset.theme;
    localStorage.removeItem(THEME_STORAGE_KEY);
  } else {
    root.dataset.theme = theme;
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  function next() {
    const value = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    applyTheme(value);
    setTheme(value);
  }

  return (
    <button
      className="secondary theme-toggle"
      type="button"
      onClick={next}
      aria-label={`Tema: ${LABEL[theme]}. Cambiar tema`}
    >
      {LABEL[theme]}
    </button>
  );
}
