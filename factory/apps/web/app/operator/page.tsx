import Link from "next/link";
import { apiGet } from "@/lib/api";
import { AutonomyPanel } from "./autonomy-panel";
import {
  DiagnosisPanel,
  type AutonomyGrant,
  type ProcessRow,
} from "./diagnosis-panel";
import { EmployeesPanel } from "./employees-panel";
import { InvitePanel } from "./invite-panel";
import {
  OPERATOR_TAB,
  OperatorTabs,
  resolveOperatorTab,
  type OperatorTabId,
} from "./operator-tabs";
import styles from "./operator.module.css";
import { ProvisionPanel } from "./provision-panel";

type Business = {
  tenant_id: string;
  name: string;
  industry: string;
  modules: string[];
  whatsapp_status: string;
  version: string;
  cost: string | null;
  autonomy?: AutonomyGrant[];
};

type Report = {
  tenantId: string;
  name: string;
  processes: ProcessRow[];
  error: string;
};

type Props = {
  searchParams?: Promise<{ tab?: string | string[] }>;
};

function industryLabel(industry: string): string {
  if (industry === "cafe") return "Cafetería";
  if (industry === "ropa") return "Ropa";
  return industry;
}

function whatsappLabel(status: string): string {
  if (status === "connected") return "Conectado";
  if (status === "own_number") return "Número propio";
  if (status === "not_connected") return "Sin conectar";
  return status;
}

function versionLabel(version: string): string {
  if (version === "published") return "Publicado";
  if (version === "draft") return "Borrador";
  return version;
}

async function loadReports(businesses: Business[]): Promise<Report[]> {
  return Promise.all(
    businesses.map(async (row) => {
      const industry = encodeURIComponent(row.industry);
      const modules = encodeURIComponent(row.modules.join(","));
      try {
        const data = await apiGet<{ processes: ProcessRow[] }>(
          `/api/operator/diagnosis?industry=${industry}&modules=${modules}`,
        );
        return { tenantId: row.tenant_id, name: row.name, processes: data.processes, error: "" };
      } catch (err) {
        return {
          tenantId: row.tenant_id,
          name: row.name,
          processes: [],
          error: err instanceof Error ? err.message : "error",
        };
      }
    }),
  );
}

function NegociosTab({
  businesses,
  reports,
  error,
}: {
  businesses: Business[];
  reports: Report[];
  error: string;
}) {
  return (
    <>
      <p className={styles.sectionHint}>
        Acá das de alta el negocio. El diagnóstico de abajo te dice qué falta y te lleva al{" "}
        <strong>Lienzo</strong> o a <strong>Autonomía</strong> para resolverlo.
      </p>
      <ProvisionPanel />
      {error ? <p className="error">{error}</p> : null}
      <h2>Lista de negocios</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Rubro</th>
              <th>WhatsApp</th>
              <th>Versión</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {businesses.map((row) => (
              <tr key={row.tenant_id}>
                <td>{row.name}</td>
                <td>{industryLabel(row.industry)}</td>
                <td>{whatsappLabel(row.whatsapp_status)}</td>
                <td>{versionLabel(row.version)}</td>
                <td>
                  <div className={styles.businessActions}>
                    <Link
                      className={styles.canvasOpen}
                      href={`/operator/flow?tenant_id=${encodeURIComponent(row.tenant_id)}`}
                    >
                      Abrir lienzo
                    </Link>
                    <Link href={`/operator?tab=empleados`}>Empleados</Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!error && businesses.length === 0 ? (
        <div className={styles.emptyBox}>
          <p>Todavía no hay negocios. Creá uno arriba para poder usar el lienzo.</p>
        </div>
      ) : null}
      {reports.map((report) => {
        const business = businesses.find((row) => row.tenant_id === report.tenantId);
        return (
          <DiagnosisPanel
            key={report.tenantId}
            tenantId={report.tenantId}
            name={report.name}
            autonomy={business?.autonomy ?? []}
            processes={report.processes}
            error={report.error || undefined}
          />
        );
      })}
    </>
  );
}

function LienzoTab({ businesses }: { businesses: Business[] }) {
  return (
    <>
      <p className={styles.sectionHint}>
        El lienzo es el mapa del negocio: WhatsApp → pedido → cobros y el resto de módulos. Elegí un
        negocio y abrilo.
      </p>
      {businesses.length === 0 ? (
        <div className={styles.emptyBox}>
          <p>No hay negocios todavía. Primero creá uno en la pestaña Negocios.</p>
          <Link href="/operator?tab=negocios">Ir a Negocios</Link>
        </div>
      ) : (
        <div className={styles.canvasGrid}>
          {businesses.map((row) => (
            <article key={row.tenant_id} className={styles.canvasCard}>
              <strong>{row.name}</strong>
              <p className="meta">
                {industryLabel(row.industry)} · {versionLabel(row.version)}
              </p>
              <Link
                className={styles.canvasOpen}
                href={`/operator/flow?tenant_id=${encodeURIComponent(row.tenant_id)}`}
              >
                Abrir lienzo
              </Link>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

function TabBody({
  tab,
  businesses,
  reports,
  error,
}: {
  tab: OperatorTabId;
  businesses: Business[];
  reports: Report[];
  error: string;
}) {
  const options = businesses.map((row) => ({ tenant_id: row.tenant_id, name: row.name }));
  if (tab === OPERATOR_TAB.LIENZO) return <LienzoTab businesses={businesses} />;
  if (tab === OPERATOR_TAB.EMPLEADOS) {
    return (
      <>
        <p className={styles.sectionHint}>
          El roster del negocio: quién atiende, con qué nombre y tono. Permisos finos → Autonomía.
          Ventas y Cobros del catálogo no se apagan.
        </p>
        {options.length === 0 ? (
          <div className={styles.emptyBox}>
            <p>Creá un negocio primero para gestionar empleados.</p>
            <Link href="/operator?tab=negocios">Ir a Negocios</Link>
          </div>
        ) : (
          <EmployeesPanel businesses={options} />
        )}
      </>
    );
  }
  if (tab === OPERATOR_TAB.AUTONOMIA) {
    return (
      <>
        <p className={styles.sectionHint}>
          Pedí más cuidado que el piso de la plantilla. No se puede aflojar la confirmación de un
          pago.
        </p>
        {options.length === 0 ? (
          <div className={styles.emptyBox}>
            <p>Creá un negocio primero para apretar autonomía.</p>
            <Link href="/operator?tab=negocios">Ir a Negocios</Link>
          </div>
        ) : (
          <AutonomyPanel businesses={options} />
        )}
      </>
    );
  }
  if (tab === OPERATOR_TAB.INVITACION) {
    return (
      <>
        <p className={styles.sectionHint}>
          Código de un solo uso para que alguien se dé de alta solo. No enciende el alta pública.
        </p>
        <InvitePanel />
      </>
    );
  }
  return <NegociosTab businesses={businesses} reports={reports} error={error} />;
}

export default async function OperatorPage({ searchParams }: Props) {
  const params = (await searchParams) ?? {};
  const rawTab = Array.isArray(params.tab) ? params.tab[0] : params.tab;
  const activeTab = resolveOperatorTab(rawTab);

  let businesses: Business[] = [];
  let reports: Report[] = [];
  let error = "";
  try {
    const data = await apiGet<{ businesses: Business[] }>("/api/operator/businesses");
    businesses = data.businesses;
    if (activeTab === OPERATOR_TAB.NEGOCIOS) {
      reports = await loadReports(businesses);
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <h1>Operador</h1>
      <p className={`lead ${styles.pageLead}`}>
        Una sección a la vez. Empezá por Negocios, después abrí el Lienzo del flujo.
      </p>
      <OperatorTabs activeTab={activeTab} />
      <TabBody tab={activeTab} businesses={businesses} reports={reports} error={error} />
    </>
  );
}
