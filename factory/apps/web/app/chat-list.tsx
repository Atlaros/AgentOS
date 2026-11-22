"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ConversationSummary } from "@/lib/api";

export function ChatList() {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const res = await fetch("/api/backend/api/conversations", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as { conversations: ConversationSummary[] };
        if (!stop) {
          setItems(data.conversations || []);
          setError("");
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "error");
      }
    }
    load();
    const id = setInterval(load, 2000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, []);

  return (
    <>
      {error ? <p className="error">No pude cargar chats ({error}). ¿API en :8000?</p> : null}
      <ul className="list">
        {items.map((c) => (
          <li key={c.id}>
            <Link className="row" href={`/chats/${c.id}`}>
              <strong>
                {c.name || c.wa_number}
                {c.needs_human ? <span className="pill">humano</span> : null}
                {c.human_takeover ? <span className="pill">Agente pausado</span> : null}
              </strong>
              <div className="meta">
                {c.message_count} msgs · {c.last_text || "—"}
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {!error && items.length === 0 ? <p className="meta">Todavía no hay chats.</p> : null}
    </>
  );
}
