import Link from "next/link";
import { apiGet } from "@/lib/api";

type CustomerRow = {
  id: string;
  name: string | null;
  wa_number: string;
  address: string | null;
  order_count: number;
  note_count: number;
  conversation_count?: number;
};

function addressSnippet(address: string | null | undefined): string {
  const clean = (address || "").replace(/\s+/g, " ").trim();
  if (!clean) return "Sin dirección";
  if (clean.length <= 72) return clean;
  return `${clean.slice(0, 69)}…`;
}

export default async function CustomersPage() {
  let rows: CustomerRow[] = [];
  let error = "";
  try {
    const data = await apiGet<{ customers: CustomerRow[] }>("/api/customers");
    rows = data.customers;
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <h1>Clientes</h1>
      <p className="lead">Cada ficha junta compras, entrega y la actividad con el agente.</p>
      {error ? <p className="error">{error}</p> : null}
      <ul className="list">
        {rows.map((customer) => (
          <li key={customer.id}>
            <Link className="row" href={`/customers/${customer.id}`}>
              <strong>{customer.name || customer.wa_number}</strong>
              <div className="meta">
                {customer.wa_number} · {addressSnippet(customer.address)} · {customer.order_count} pedidos
                {typeof customer.conversation_count === "number" ? ` · ${customer.conversation_count} chats` : ""}
                {" · "}
                {customer.note_count} notas
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {!error && rows.length === 0 ? <p className="meta">Todavía no hay clientes.</p> : null}
    </>
  );
}
