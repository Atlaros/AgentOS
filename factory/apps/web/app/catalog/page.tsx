import Link from "next/link";

import { OpenableProductThumb } from "@/components/openable-product-thumb";
import { apiGet } from "@/lib/api";

import { AddProductForm } from "./add-form";
import { ComboForm } from "./combo-form";
import { ModifierForm } from "./modifier-form";
import { AvailabilityButton } from "./availability-button";
import { CatalogSearch } from "./catalog-search";
import styles from "./catalog.module.css";
import { EditProductForm, type EditableProduct } from "./edit-form";
import { StockCell } from "./stock-cell";

type Product = EditableProduct & {
  season?: string;
  style?: string;
  test_only?: boolean;
  available?: boolean;
  sold?: boolean;
  sold_units?: number;
  media_id?: string;
  thumb_url?: string;
  image_url?: string;
};

type CatalogPageProps = {
  searchParams: Promise<{ q?: string | string[]; edit?: string | string[] }>;
};

function readQuery(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw || "").trim();
}

function withParams(q: string, extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  for (const [key, value] of Object.entries(extra || {})) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return query ? `/catalog?${query}` : "/catalog";
}

export default async function CatalogPage({ searchParams }: CatalogPageProps) {
  const params = await searchParams;
  const q = readQuery(params.q);
  const edit = readQuery(params.edit);
  const query = new URLSearchParams({ limit: "200" });
  if (q) query.set("q", q);
  let products: Product[] = [];
  let error = "";
  try {
    const data = await apiGet<{ products: Product[] }>(`/api/catalog?${query.toString()}`);
    products = data.products;
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  const editing = products.find((product) => product.variant_sku === edit) ?? null;

  return (
    <>
      <h1>Inventario</h1>
      <p className="lead">
        Ajustá el stock del día en la columna Stock (Enter o salir del campo guarda). Alta rápida:
        código, nombre, categoría, precio y cantidad. Lo demás queda en «Más detalles».
      </p>
      <CatalogSearch q={q} />
      <AddProductForm />
      <details className={styles.advancedBlock}>
        <summary>Combos y modificadores (opcional)</summary>
        <ComboForm />
        <ModifierForm />
      </details>
      {editing ? <EditProductForm product={editing} closeHref={withParams(q)} /> : null}
      <p className={`meta ${styles.hint}`}>
        {q
          ? `${products.length} coincidencias para «${q}».`
          : `${products.length} productos en la tabla.`}
      </p>
      {error ? <p className="error">{error}</p> : null}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th aria-label="Foto" />
              <th>Código</th>
              <th>Nombre</th>
              <th>Categoría</th>
              <th>Precio</th>
              <th>Stock</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => {
              const available = p.available !== false;
              const rowClass = [
                available ? "" : "row-sold",
                p.variant_sku === edit ? styles.rowEditing : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <tr key={p.variant_sku} className={rowClass || undefined}>
                  <td className={styles.thumbCell}>
                    <OpenableProductThumb
                      name={p.name}
                      thumbUrl={p.thumb_url}
                      imageUrl={p.image_url}
                      size="sm"
                    />
                  </td>
                  <td>{p.codigo || "—"}</td>
                  <td>
                    {p.name}
                    {p.test_only ? <span className="pill">prueba</span> : null}
                  </td>
                  <td>{p.category}</td>
                  <td className={styles.num}>
                    {p.price} {p.currency}
                  </td>
                  <td>
                    <StockCell variantSku={p.variant_sku} stock={p.stock} />
                  </td>
                  <td>{available ? "Disponible" : "Agotado"}</td>
                  <td>
                    <div className={styles.rowActions}>
                      <Link className={styles.rowAction} href={withParams(q, { edit: p.variant_sku })}>
                        Editar
                      </Link>
                      <AvailabilityButton variantSku={p.variant_sku} available={available} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!error && products.length === 0 ? (
        <p className="meta">{q ? "Ningún producto coincide con la búsqueda." : "Todavía no hay productos."}</p>
      ) : null}
    </>
  );
}
