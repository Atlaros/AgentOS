import styles from "./catalog.module.css";

export function CatalogSearch({ q }: { q: string }) {
  return (
    <form className={styles.search} action="/catalog" method="get">
      <label>
        Buscar producto
        <input
          name="q"
          defaultValue={q}
          placeholder="Código, nombre, categoría…"
          autoComplete="off"
        />
      </label>
      <button type="submit">Buscar</button>
      {q ? (
        <a className={styles.clear} href="/catalog">
          Ver todas
        </a>
      ) : null}
    </form>
  );
}
