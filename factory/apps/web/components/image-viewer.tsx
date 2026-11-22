"use client";

import { useEffect, useId, useRef, useState } from "react";

import styles from "./image-viewer.module.css";

export type ImageViewerProps = {
  open: boolean;
  onClose: () => void;
  sources: string[];
  alt?: string;
  title?: string;
};

export function ImageViewer({ open, onClose, sources, alt = "", title }: ImageViewerProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [index, setIndex] = useState(0);
  const total = sources.length;
  const current = total > 0 ? sources[Math.min(index, total - 1)] : "";

  useEffect(() => {
    if (!open) return;
    setIndex(0);
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (total < 2) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        setIndex((value) => (value + 1) % total);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setIndex((value) => (value - 1 + total) % total);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [open, onClose, total]);

  if (!open || total === 0) return null;

  return (
    <div
      className={styles.backdrop}
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title || alt || "Foto"}
          </h2>
          <button ref={closeRef} type="button" className={`secondary ${styles.close}`} onClick={onClose}>
            Cerrar
          </button>
        </header>
        <div className={styles.stage}>
          {/* eslint-disable-next-line @next/next/no-img-element -- authenticated media proxy */}
          <img className={styles.image} src={current} alt={alt || title || "Foto del producto"} />
        </div>
        {total > 1 ? (
          <div className={styles.nav}>
            <button
              type="button"
              className="secondary"
              onClick={() => setIndex((value) => (value - 1 + total) % total)}
            >
              Anterior
            </button>
            <span className={styles.counter}>
              {index + 1} / {total}
            </span>
            <button
              type="button"
              className="secondary"
              onClick={() => setIndex((value) => (value + 1) % total)}
            >
              Siguiente
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
