import styles from "./orders.module.css";

export function OrdersSearch({ q }: { q: string }) {
  return (
    <form className={styles.search} action="/orders" method="get">
      <label>
        Buscar pedido
        <input
          name="q"
          defaultValue={q}
          placeholder="Nombre, teléfono o nº de pedido"
          autoComplete="off"
        />
      </label>
      <button type="submit">Buscar</button>
      {q ? (
        <a className={styles.clear} href="/orders">
          Ver todos
        </a>
      ) : null}
    </form>
  );
}
