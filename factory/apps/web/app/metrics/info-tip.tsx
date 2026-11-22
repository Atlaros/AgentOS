"use client";

import { useId, useState } from "react";

import styles from "./metrics.module.css";

type InfoTipProps = {
  label: string;
  text: string;
};

export function InfoTip({ label, text }: InfoTipProps) {
  const tipId = useId();
  const [pinned, setPinned] = useState(false);

  return (
    <span className={styles.tipWrap} data-open={pinned ? "true" : "false"}>
      <button
        type="button"
        className={styles.tipButton}
        aria-label={label}
        aria-expanded={pinned}
        aria-describedby={tipId}
        onClick={() => setPinned((open) => !open)}
        onKeyDown={(event) => {
          if (event.key !== "Escape") return;
          setPinned(false);
          event.currentTarget.blur();
        }}
      >
        <span aria-hidden="true">ⓘ</span>
      </button>
      <span role="tooltip" id={tipId} className={styles.tip}>
        {text}
      </span>
    </span>
  );
}
