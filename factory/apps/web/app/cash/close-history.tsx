"use client";

import { formatCashWhen } from "./cash-form";
import styles from "./cash.module.css";
import type { CashSession } from "./session-panel";

export function CloseHistory({ closes }: { closes: CashSession[] }) {
  return (
    <section aria-labelledby="cash-history-title">
      <h2 id="cash-history-title" className={styles.sectionTitle}>
        Historial de cierres
      </h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Esperado</th>
              <th>Contado</th>
              <th>Diferencia</th>
              <th>Nota</th>
            </tr>
          </thead>
          <tbody>
            {closes.length === 0 ? (
              <tr>
                <td colSpan={5}>Todavía no hay cierres.</td>
              </tr>
            ) : (
              closes.map((item) => {
                const diff = item.difference || "0.00";
                const nonzero = Number(String(diff).replace(",", ".")) !== 0;
                return (
                  <tr key={item.id}>
                    <td className={styles.num}>{formatCashWhen(item.closed_at || item.opened_at)}</td>
                    <td className={styles.num}>{item.expected_cash} BOB</td>
                    <td className={styles.num}>{item.counted_cash || "—"} BOB</td>
                    <td className={nonzero ? styles.diffNonzero : styles.diffZero}>
                      <span className={styles.num}>{diff} BOB</span>
                    </td>
                    <td>{item.close_note || "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
