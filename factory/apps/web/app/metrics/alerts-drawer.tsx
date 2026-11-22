"use client";

import { useRef } from "react";

import styles from "./metrics.module.css";
import { ThresholdsForm, type ThresholdValues } from "./thresholds-form";

type AlertsDrawerProps = {
  thresholds: ThresholdValues;
};

export function AlertsDrawer({ thresholds }: AlertsDrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);

  function open() {
    dialogRef.current?.showModal();
  }

  function close() {
    dialogRef.current?.close();
  }

  return (
    <>
      <button ref={openerRef} type="button" className={styles.alertButton} onClick={open}>
        ⚙ Alertas
      </button>
      <dialog
        ref={dialogRef}
        className={styles.drawer}
        aria-labelledby="analytics-alerts-title"
        onClick={(event) => {
          if (event.target === dialogRef.current) close();
        }}
        onClose={() => openerRef.current?.focus()}
      >
        <div className={styles.drawerPanel}>
          <header className={styles.drawerHeader}>
            <h2 id="analytics-alerts-title">Alertas</h2>
            <button type="button" className="secondary" onClick={close}>
              Cerrar
            </button>
          </header>
          <ThresholdsForm initial={thresholds} />
        </div>
      </dialog>
    </>
  );
}
