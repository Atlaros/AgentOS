"use client";

import { useState } from "react";

import { isHttpUrl, proxyMediaUrl } from "./media-url";
import styles from "./product-thumb.module.css";

const THUMB_SIZE = {
  sm: "sm",
  md: "md",
  lg: "lg",
  xl: "xl",
  fill: "fill",
} as const;

type ThumbSize = (typeof THUMB_SIZE)[keyof typeof THUMB_SIZE];

export type ProductThumbProps = {
  name: string;
  initial?: string;
  thumbUrl?: string | null;
  imageUrl?: string | null;
  size?: ThumbSize;
  className?: string;
  onOpen?: () => void;
};

function letterFor(name: string, initial?: string): string {
  const raw = (initial || name || "?").trim();
  return (raw.slice(0, 1) || "?").toUpperCase();
}

function resolveSrc(thumbUrl?: string | null, imageUrl?: string | null): string | undefined {
  const fromThumb = proxyMediaUrl(thumbUrl);
  if (fromThumb) return fromThumb;
  if (isHttpUrl(imageUrl)) return imageUrl!.trim();
  return undefined;
}

export function ProductThumb({
  name,
  initial,
  thumbUrl,
  imageUrl,
  size = THUMB_SIZE.md,
  className,
  onOpen,
}: ProductThumbProps) {
  const [failed, setFailed] = useState(false);
  const src = !failed ? resolveSrc(thumbUrl, imageUrl) : undefined;
  const letter = letterFor(name, initial);
  const sizeClass = styles[size] || styles.md;
  const extra = className ? ` ${className}` : "";

  const body = src ? (
    // eslint-disable-next-line @next/next/no-img-element -- authenticated media proxy, not public CDN
    <img
      className={styles.photo}
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  ) : (
    <span className={styles.initial} aria-hidden="true">
      {letter}
    </span>
  );

  if (onOpen && src) {
    return (
      <button
        type="button"
        className={`${styles.button} ${sizeClass}${extra}`}
        onClick={(event) => {
          event.stopPropagation();
          onOpen();
        }}
        aria-label={`Ver foto de ${name}`}
      >
        {body}
      </button>
    );
  }

  return (
    <span className={`${styles.wrap} ${sizeClass}${extra}`} aria-hidden={src ? undefined : true}>
      {body}
    </span>
  );
}

export { resolveSrc as resolveProductThumbSrc };
