import { apiGet } from "@/lib/api";
import { ResetSecretForm } from "./reset-secret-form";
import { UserForm } from "./user-form";

type PanelUser = {
  id: string;
  name: string;
  email: string;
  role: string;
  job_title?: string;
};

type AuditEvent = {
  id: string;
  actor_name: string;
  actor_role: string;
  method: string;
  path: string;
  created_at: string | null;
};

export default async function SettingsPage() {
  let users: PanelUser[] = [];
  let events: AuditEvent[] = [];
  let error = "";
  let actorRole = "";
  try {
    const me = await apiGet<{ role: string }>("/api/panel/me");
    actorRole = me.role;
    const listed = await apiGet<{ users: PanelUser[] }>("/api/panel/users");
    const audit = await apiGet<{ events: AuditEvent[] }>("/api/panel/audit");
    users = listed.users;
    events = audit.events;
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <h1>Configuración</h1>
      <p className="lead">
        Cada persona entra con su clave. Una escritura del panel queda a su nombre, no a nombre del empleado digital.
      </p>
      {error ? <p className="error">{error}</p> : null}
      <UserForm />
      <h2 className="section-title">Usuarios</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={3}>Todavía no hay usuarios además del acceso inicial.</td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id}>
                  <td>{user.name}</td>
                  <td>{user.email}</td>
                  <td>
                    {user.role === "admin"
                      ? "Administrador"
                      : user.role === "owner"
                        ? "Dueño"
                        : user.role === "supervisor"
                          ? "Supervisor"
                          : user.job_title
                            ? `Equipo · ${user.job_title}`
                            : "Equipo"}
                    {actorRole === "admin" ? (
                      <ResetSecretForm userId={user.id} userName={user.name} />
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <h2 className="section-title">Auditoría</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Persona</th>
              <th>Rol</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={3}>Todavía no hay escrituras.</td>
              </tr>
            ) : (
              events
                .slice()
                .reverse()
                .map((event) => (
                  <tr key={event.id}>
                    <td>{event.actor_name}</td>
                    <td>{event.actor_role === "owner" ? "Dueño" : "Equipo"}</td>
                    <td>
                      <code>
                        {event.method} {event.path}
                      </code>
                    </td>
                  </tr>
                ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
