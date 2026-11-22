"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function UserForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("staff");
  const [jobTitle, setJobTitle] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/backend/api/panel/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, role, secret, job_title: jobTitle }),
      });
      if (!response.ok) {
        setError("No se pudo agregar la persona.");
        return;
      }
      setName("");
      setEmail("");
      setSecret("");
      setRole("staff");
      setJobTitle("");
      router.refresh();
    } catch {
      setError("No se pudo agregar la persona.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <label htmlFor="panel-name">Nombre</label>
      <input id="panel-name" value={name} onChange={(event) => setName(event.target.value)} required />
      <label htmlFor="panel-email">Correo</label>
      <input
        id="panel-email"
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />
      <label htmlFor="panel-role">Rol</label>
      <select id="panel-role" value={role} onChange={(event) => setRole(event.target.value)}>
        <option value="staff">Equipo</option>
        <option value="supervisor">Supervisor</option>
      </select>
      {role === "staff" ? (
        <>
          <label htmlFor="panel-job">Puesto</label>
          <input
            id="panel-job"
            value={jobTitle}
            onChange={(event) => setJobTitle(event.target.value)}
            maxLength={40}
          />
        </>
      ) : null}
      <label htmlFor="panel-secret">Clave</label>
      <input
        id="panel-secret"
        type="password"
        value={secret}
        onChange={(event) => setSecret(event.target.value)}
        minLength={8}
        required
      />
      <button type="submit" disabled={pending}>
        {pending ? "Agregando…" : "Agregar persona"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
