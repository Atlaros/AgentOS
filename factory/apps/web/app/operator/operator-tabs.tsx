import Link from "next/link";

import styles from "./operator.module.css";

export const OPERATOR_TAB = {
  NEGOCIOS: "negocios",
  LIENZO: "lienzo",
  EMPLEADOS: "empleados",
  AUTONOMIA: "autonomia",
  INVITACION: "invitacion",
} as const;

export type OperatorTabId = (typeof OPERATOR_TAB)[keyof typeof OPERATOR_TAB];

const TAB_IDS = [
  OPERATOR_TAB.NEGOCIOS,
  OPERATOR_TAB.LIENZO,
  OPERATOR_TAB.EMPLEADOS,
  OPERATOR_TAB.AUTONOMIA,
  OPERATOR_TAB.INVITACION,
] as const;

const TAB_LABELS: Record<OperatorTabId, string> = {
  negocios: "Negocios",
  lienzo: "Lienzo",
  empleados: "Empleados",
  autonomia: "Autonomía",
  invitacion: "Invitación",
};

export function resolveOperatorTab(raw: string | undefined): OperatorTabId {
  if (raw === OPERATOR_TAB.LIENZO) return OPERATOR_TAB.LIENZO;
  if (raw === OPERATOR_TAB.EMPLEADOS) return OPERATOR_TAB.EMPLEADOS;
  if (raw === OPERATOR_TAB.AUTONOMIA) return OPERATOR_TAB.AUTONOMIA;
  if (raw === OPERATOR_TAB.INVITACION) return OPERATOR_TAB.INVITACION;
  return OPERATOR_TAB.NEGOCIOS;
}

function tabHref(tab: OperatorTabId): string {
  return `/operator?tab=${tab}`;
}

export function OperatorTabs({ activeTab }: { activeTab: OperatorTabId }) {
  return (
    <nav className={styles.tabNav} aria-label="Secciones de operador">
      <div className={styles.tabList} role="tablist">
        {TAB_IDS.map((tab) => {
          const selected = tab === activeTab;
          return (
            <Link
              key={tab}
              href={tabHref(tab)}
              role="tab"
              aria-selected={selected}
              className={selected ? styles.tabSelected : styles.tab}
              scroll={false}
            >
              {TAB_LABELS[tab]}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
