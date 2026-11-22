import Link from "next/link";

import styles from "./operator.module.css";

export type AutonomyGrant = { action: string; level: string };

export type ProcessRow = {
  process_id: string;
  title: string;
  status: string;
  evidence: string[];
  gaps: string[];
};

type Props = {
  tenantId: string;
  name: string;
  autonomy: AutonomyGrant[];
  processes: ProcessRow[];
  error?: string;
};

const MODULE_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  mostrador: "Mostrador",
  pedido: "Pedido",
  cobros: "Cobros",
  caja: "Caja",
  catalogo: "Catálogo",
  proveedores: "Proveedores",
  barra: "Barra",
  aprobacion: "Aprobación",
  analitica: "Analítica",
  contabilidad: "Contabilidad",
  reportes: "Reportes",
  conocimiento: "Conocimiento",
};

function moduleLabel(id: string): string {
  return MODULE_LABELS[id] ?? id;
}

function actionLabel(action: string): string {
  if (action === "confirm_payment") return "Confirmar un pago";
  if (action === "post_journal") return "Asiento contable";
  if (action === "adjust_stock") return "Ajuste de stock";
  if (action === "reply_customer") return "Respuesta al cliente";
  return action;
}

function autonomyLabel(level: string): string {
  if (level === "never") return "Nunca";
  if (level === "recommend") return "Solo recomendar";
  if (level === "approval") return "Con aprobación";
  if (level === "within_limits") return "Dentro de límites";
  return level;
}

function statusLabel(status: string): string {
  if (status === "covered") return "Cubierto";
  if (status === "partial") return "Parcial";
  if (status === "gap") return "Hueco";
  return status;
}

function processHint(process: ProcessRow): string {
  if (process.status === "covered") {
    return "Este proceso ya tiene los módulos que necesita.";
  }
  if (process.status === "partial") {
    const have = process.evidence.map(moduleLabel).join(", ");
    const need = process.gaps.map(moduleLabel).join(", ");
    return `Ya está ${have}. Falta sumar ${need} en el lienzo y publicar.`;
  }
  const need = process.gaps.map(moduleLabel).join(", ");
  return `Arrastrá al lienzo: ${need}. Después publicá el mapa.`;
}

function openCount(processes: ProcessRow[]): number {
  return processes.filter((row) => row.status !== "covered").length;
}

export function DiagnosisPanel({ tenantId, name, autonomy, processes, error }: Props) {
  const flowHref = `/operator/flow?tenant_id=${encodeURIComponent(tenantId)}`;
  const open = openCount(processes);

  return (
    <section className={styles.diagnosis} aria-labelledby={`diagnosis-${tenantId}`}>
      <header className={styles.diagnosisHeader}>
        <div>
          <p className={styles.diagnosisEyebrow}>Diagnóstico</p>
          <h2 id={`diagnosis-${tenantId}`} className={styles.diagnosisTitle}>
            {name}
          </h2>
          <p className={styles.diagnosisLead}>
            {open === 0
              ? "Los procesos del rubro están cubiertos. Revisá autonomía si querés más cuidado."
              : `${open} proceso${open === 1 ? "" : "s"} sin completar. El lienzo es donde se resuelven.`}
          </p>
        </div>
        <div className={styles.diagnosisHeaderActions}>
          <Link className={styles.diagnosisPrimary} href={flowHref}>
            {open === 0 ? "Ver lienzo" : "Completar en el lienzo"}
          </Link>
          <Link className={styles.diagnosisGhost} href="/operator?tab=autonomia">
            Ajustar autonomía
          </Link>
        </div>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <div className={styles.diagnosisGrid}>
        <article className={styles.diagnosisBlock}>
          <div className={styles.diagnosisBlockHead}>
            <h3>Autonomía</h3>
            <p>Qué puede hacer solo el equipo digital. El dueño solo puede apretar, no aflojar pagos.</p>
          </div>
          <ul className={styles.grantList}>
            {autonomy.length === 0 ? (
              <li className={styles.grantEmpty}>Sin grants cargados todavía.</li>
            ) : (
              autonomy.map((grant) => (
                <li key={grant.action} className={styles.grantRow}>
                  <span>{actionLabel(grant.action)}</span>
                  <span className={styles.grantLevel}>{autonomyLabel(grant.level)}</span>
                </li>
              ))
            )}
          </ul>
          <Link className={styles.diagnosisInlineLink} href="/operator?tab=autonomia">
            Ir a Autonomía →
          </Link>
        </article>

        <article className={styles.diagnosisBlock}>
          <div className={styles.diagnosisBlockHead}>
            <h3>Procesos del rubro</h3>
            <p>Cada hueco se cierra sumando los módulos faltantes en el lienzo y publicando.</p>
          </div>
          <ul className={styles.processList}>
            {processes.map((process) => {
              const covered = process.status === "covered";
              return (
                <li
                  key={process.process_id}
                  className={styles.processCard}
                  data-status={process.status}
                >
                  <div className={styles.processTop}>
                    <strong>{process.title}</strong>
                    <span className={styles.statusPill} data-status={process.status}>
                      <span className={styles.statusDot} aria-hidden="true" />
                      {statusLabel(process.status)}
                    </span>
                  </div>
                  <p className={styles.processHint}>{processHint(process)}</p>
                  {!covered && process.gaps.length > 0 ? (
                    <div className={styles.gapChips} aria-label="Módulos que faltan">
                      {process.gaps.map((gap) => (
                        <span key={gap} className={styles.gapChip}>
                          {moduleLabel(gap)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className={styles.processActions}>
                    <Link className={covered ? styles.diagnosisGhost : styles.diagnosisPrimary} href={flowHref}>
                      {covered ? "Abrir lienzo" : "Resolver en el lienzo"}
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        </article>
      </div>
    </section>
  );
}
