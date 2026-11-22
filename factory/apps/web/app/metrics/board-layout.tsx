"use client";

import { useEffect, useState, type ReactNode } from "react";

import styles from "./metrics.module.css";

interface BoardLayoutProps {
  main: ReactNode;
  aside: ReactNode;
}

const NARROW = "(max-width: 900px)";

export function BoardLayout({ main, aside }: BoardLayoutProps) {
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(NARROW);
    const sync = () => setNarrow(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return (
    <div className={styles.board} data-metrics-board="1">
      <div className={styles.main}>{main}</div>
      <aside className={styles.aside} aria-label="Analista">
        {narrow ? (
          <details className={styles.analystFold}>
            <summary>Preguntá al Analista</summary>
            {aside}
          </details>
        ) : (
          <div className={styles.analystPanel}>{aside}</div>
        )}
      </aside>
    </div>
  );
}
