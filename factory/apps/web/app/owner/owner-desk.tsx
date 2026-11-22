"use client";

import { useEffect, useState } from "react";

type AutonomyGrant = { action: string; level: string };

type OwnedBusiness = {
  name: string;
  industry: string;
  whatsapp_status: string;
  whatsapp_phone_id?: string;
  whatsapp_token_set?: boolean;
  autonomy?: AutonomyGrant[];
};

export function OwnerDesk() {
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [business, setBusiness] = useState<OwnedBusiness | null>(null);
  const [phone, setPhone] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [tokenSaved, setTokenSaved] = useState(false);
  const [reply, setReply] = useState("");
  const [left, setLeft] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [autonomyAction, setAutonomyAction] = useState("adjust_stock");
  const [autonomyLevel, setAutonomyLevel] = useState("never");
  const [autonomyNote, setAutonomyNote] = useState("");
  type EmployeeRow = {
    employee_key: string;
    base_role: string;
    display_name: string;
    style: string;
    enabled: boolean;
    is_clone: boolean;
    locked: boolean;
  };
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [employeeNote, setEmployeeNote] = useState("");
  const [cloneRole, setCloneRole] = useState("sales");
  const [cloneName, setCloneName] = useState("");

  async function loadEmployees() {
    const response = await fetch("/api/owner/employees", { cache: "no-store" });
    if (!response.ok) return;
    const body = (await response.json()) as { employees?: EmployeeRow[] };
    setEmployees(body.employees || []);
  }

  useEffect(() => {
    let cancelled = false;
    fetch("/api/owner/session", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok || cancelled) return;
        const loaded = (await response.json()) as OwnedBusiness;
        setBusiness(loaded);
        setTokenSaved(Boolean(loaded.whatsapp_token_set));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!business) return;
    let cancelled = false;
    fetch("/api/owner/messages", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok || cancelled) return;
        const body = (await response.json()) as { messages?: { text?: string; delivered?: boolean }[] };
        const last = body.messages?.at(-1);
        if (last?.text) {
          setReply(last.text);
          setLeft(Boolean(last.delivered));
        }
      })
      .catch(() => undefined);
    void loadEmployees().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [business]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const opened = await fetch("/api/owner/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, secret }),
      });
      if (!opened.ok) throw new Error("No se pudo entrar.");
      setSecret("");
      const loaded = await fetch("/api/owner/session", { cache: "no-store" });
      if (!loaded.ok) throw new Error("No se pudo entrar.");
      const businessBody = (await loaded.json()) as OwnedBusiness;
      setBusiness(businessBody);
      setTokenSaved(Boolean(businessBody.whatsapp_token_set));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo entrar.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");
    try {
      await fetch("/api/owner/session", { method: "DELETE" });
      setBusiness(null);
      setReply("");
      setLeft(false);
      setTokenSaved(false);
      setAutonomyNote("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo salir.");
    } finally {
      setBusy(false);
    }
  }

  async function tightenAutonomy(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setAutonomyNote("");
    try {
      const response = await fetch("/api/owner/autonomy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: autonomyAction, level: autonomyLevel }),
      });
      const body = (await response.json()) as {
        error?: string;
        autonomy?: AutonomyGrant[];
      };
      if (!response.ok) {
        if (body.error === "autonomy_floor") {
          throw new Error("Eso aflojaría el piso. Solo se puede pedir más cuidado.");
        }
        throw new Error("No se pudo apretar la autonomía.");
      }
      const loaded = await fetch("/api/owner/session", { cache: "no-store" });
      if (!loaded.ok) throw new Error("No se pudo apretar la autonomía.");
      setBusiness((await loaded.json()) as OwnedBusiness);
      const grant = body.autonomy?.find((item) => item.action === autonomyAction);
      setAutonomyNote(
        grant ? `Listo: ${grant.action} quedó en ${grant.level}.` : "Autonomía actualizada.",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo apretar la autonomía.");
    } finally {
      setBusy(false);
    }
  }

  async function savePhone(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await fetch("/api/owner/whatsapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone_number_id: phone,
          ...(accessToken ? { access_token: accessToken } : {}),
        }),
      });
      if (!saved.ok) {
        const body = (await saved.json()) as { error?: string };
        if (body.error === "pilot_phone_reserved") {
          throw new Error("Ese identificador es del canal que ya está en marcha.");
        }
        if (body.error === "pilot_token_reserved") {
          throw new Error("Ese token es del canal que ya está en marcha.");
        }
        if (body.error === "phone_taken") {
          throw new Error("Ese identificador ya pertenece a otro negocio.");
        }
        throw new Error("No se pudo guardar el identificador.");
      }
      const savedBody = (await saved.json()) as { whatsapp_token_set?: boolean };
      setTokenSaved(Boolean(savedBody.whatsapp_token_set));
      setPhone("");
      setAccessToken("");
      const loaded = await fetch("/api/owner/session", { cache: "no-store" });
      if (!loaded.ok) throw new Error("No se pudo guardar el identificador.");
      setBusiness((await loaded.json()) as OwnedBusiness);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo guardar el identificador.");
    } finally {
      setBusy(false);
    }
  }

  if (business) {
    const whatsapp =
      business.whatsapp_status === "connected"
        ? "WhatsApp conectado"
        : business.whatsapp_status === "own_number"
          ? "Este número está listo"
          : "WhatsApp no está conectado";
    const reserved = business.whatsapp_phone_id
      ? `Identificador ${business.whatsapp_phone_id}. `
      : "";
    return (
      <section className="login-card">
        <h1>{business.name}</h1>
        <p className="lead">{business.industry}</p>
        <p>
          {reserved}
          {whatsapp}
        </p>
        {tokenSaved ? <p>Token guardado. La próxima respuesta sale por este número.</p> : null}
        {reply && left ? <p>Salió por este número. {reply}</p> : null}
        {reply && !left ? <p>Respuesta guardada en este negocio. No salió. {reply}</p> : null}
        <form className="login-form" onSubmit={savePhone}>
          <label htmlFor="whatsapp-phone">Identificador de WhatsApp</label>
          <input
            id="whatsapp-phone"
            inputMode="numeric"
            autoComplete="off"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            required
          />
          <label htmlFor="whatsapp-token">Token de Meta</label>
          <input
            id="whatsapp-token"
            type="password"
            autoComplete="off"
            value={accessToken}
            onChange={(event) => setAccessToken(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Guardando…" : "Guardar número"}
          </button>
          {error ? <p className="error">{error}</p> : null}
        </form>
        <section aria-labelledby="owner-employees-title">
          <h2 id="owner-employees-title">Empleados</h2>
          <p className="meta">
            Activá o renombrá roles del catálogo. Podés clonar un rol base; el estilo no da
            permisos. Ventas y cobros no se apagan.
          </p>
          <ul className="meta">
            {employees.map((row) => (
              <li key={row.employee_key}>
                <strong>{row.display_name}</strong> ({row.base_role}
                {row.is_clone ? ", propio" : ""}){" "}
                <label>
                  <input
                    type="checkbox"
                    checked={row.enabled}
                    disabled={busy || row.locked}
                    onChange={(event) => {
                      void (async () => {
                        setBusy(true);
                        setError("");
                        setEmployeeNote("");
                        try {
                          const response = await fetch("/api/owner/employees", {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                              employee_key: row.employee_key,
                              enabled: event.target.checked,
                            }),
                          });
                          if (!response.ok) throw new Error("No se pudo actualizar.");
                          await loadEmployees();
                          setEmployeeNote("Empleado actualizado.");
                        } catch (cause) {
                          setError(
                            cause instanceof Error ? cause.message : "No se pudo actualizar.",
                          );
                        } finally {
                          setBusy(false);
                        }
                      })();
                    }}
                  />{" "}
                  activo
                </label>{" "}
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => {
                    const next = window.prompt("Nombre", row.display_name);
                    if (!next || next.trim() === row.display_name) return;
                    void (async () => {
                      setBusy(true);
                      setError("");
                      try {
                        const response = await fetch("/api/owner/employees", {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            employee_key: row.employee_key,
                            display_name: next.trim(),
                          }),
                        });
                        if (!response.ok) throw new Error("No se pudo renombrar.");
                        await loadEmployees();
                        setEmployeeNote("Nombre actualizado.");
                      } catch (cause) {
                        setError(
                          cause instanceof Error ? cause.message : "No se pudo renombrar.",
                        );
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                >
                  Renombrar
                </button>
                {row.is_clone ? (
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      void (async () => {
                        setBusy(true);
                        setError("");
                        try {
                          const response = await fetch("/api/owner/employees", {
                            method: "DELETE",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ employee_key: row.employee_key }),
                          });
                          if (!response.ok) throw new Error("No se pudo archivar.");
                          await loadEmployees();
                          setEmployeeNote("Empleado archivado.");
                        } catch (cause) {
                          setError(
                            cause instanceof Error ? cause.message : "No se pudo archivar.",
                          );
                        } finally {
                          setBusy(false);
                        }
                      })();
                    }}
                  >
                    Archivar
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          <form
            className="login-form"
            onSubmit={(event) => {
              event.preventDefault();
              void (async () => {
                setBusy(true);
                setError("");
                setEmployeeNote("");
                try {
                  const response = await fetch("/api/owner/employees", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      base_role: cloneRole,
                      display_name: cloneName,
                    }),
                  });
                  if (!response.ok) throw new Error("No se pudo crear el empleado.");
                  setCloneName("");
                  await loadEmployees();
                  setEmployeeNote("Empleado creado.");
                } catch (cause) {
                  setError(
                    cause instanceof Error ? cause.message : "No se pudo crear el empleado.",
                  );
                } finally {
                  setBusy(false);
                }
              })();
            }}
          >
            <label htmlFor="owner-clone-role">Crear desde rol</label>
            <select
              id="owner-clone-role"
              value={cloneRole}
              onChange={(event) => setCloneRole(event.target.value)}
            >
              <option value="sales">Ventas</option>
              <option value="collections">Cobros</option>
              <option value="ops">Operaciones</option>
              <option value="postventa">Postventa</option>
              <option value="inventory">Inventario</option>
            </select>
            <label htmlFor="owner-clone-name">Nombre</label>
            <input
              id="owner-clone-name"
              value={cloneName}
              onChange={(event) => setCloneName(event.target.value)}
              required
            />
            <button type="submit" disabled={busy || !cloneName.trim()}>
              Crear empleado
            </button>
          </form>
          {employeeNote ? <p className="meta">{employeeNote}</p> : null}
        </section>
        <form className="login-form" onSubmit={tightenAutonomy}>
          <label htmlFor="owner-autonomy-action">Pedir más cuidado</label>
          <select
            id="owner-autonomy-action"
            value={autonomyAction}
            onChange={(event) => setAutonomyAction(event.target.value)}
          >
            <option value="adjust_stock">Ajuste de stock</option>
            <option value="post_journal">Asiento contable</option>
            <option value="reply_customer">Respuesta al cliente</option>
            <option value="confirm_payment">Confirmar un pago</option>
          </select>
          <label htmlFor="owner-autonomy-level">Nivel</label>
          <select
            id="owner-autonomy-level"
            value={autonomyLevel}
            onChange={(event) => setAutonomyLevel(event.target.value)}
          >
            <option value="never">Nunca</option>
            <option value="recommend">Solo recomendar</option>
            <option value="approval">Con aprobación</option>
            <option value="within_limits">Dentro de límites</option>
          </select>
          <button type="submit" disabled={busy}>
            {busy ? "Guardando…" : "Apretar autonomía"}
          </button>
          {autonomyNote ? <p className="meta">{autonomyNote}</p> : null}
          {business.autonomy?.length ? (
            <ul className="meta">
              {business.autonomy.map((grant) => (
                <li key={grant.action}>
                  {grant.action}: {grant.level}
                </li>
              ))}
            </ul>
          ) : null}
        </form>
        <p>
          <button type="button" className="secondary" disabled={busy} onClick={logout}>
            Salir
          </button>
        </p>
      </section>
    );
  }

  return (
    <section className="login-card">
      <h1>Tu negocio</h1>
      <p className="lead">Entra con el correo y la clave que te dio el alta.</p>
      <form className="login-form" onSubmit={submit}>
        <label htmlFor="business-email">Correo</label>
        <input
          id="business-email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <label htmlFor="business-secret">Clave</label>
        <input
          id="business-secret"
          type="password"
          autoComplete="current-password"
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          required
        />
        <button type="submit" disabled={busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </section>
  );
}
