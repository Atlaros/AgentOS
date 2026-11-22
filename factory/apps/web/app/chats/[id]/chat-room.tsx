"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ImageViewer } from "@/components/image-viewer";
import { proxyMediaUrl } from "@/components/media-url";
import styles from "./chat-room.module.css";
import { ReplyForm } from "./reply-form";
import { Thread } from "./thread";

export type ChatMessageMedia = {
  asset_id?: string | null;
  kind?: string;
  mime?: string | null;
  filename?: string | null;
  size_bytes?: number | null;
  thumb_url?: string | null;
  status?: string;
  origin?: string | null;
};

export type ChatMessage = {
  role: string;
  text: string;
  media?: ChatMessageMedia | null;
};

export type ConversationFile = ChatMessageMedia & {
  id?: string;
  direction?: string;
  error?: string | null;
  uploaded_by?: string | null;
  created_at?: string | null;
  transcript_text?: string | null;
  summary_text?: string | null;
  enrichment_status?: string | null;
  enrichment_error?: string | null;
};

export type CartLine = {
  variant_sku?: string;
  name: string;
  quantity: number;
  unit_price: string;
  currency: string;
};

export type CartView = {
  lines: CartLine[];
  discount: string;
  total: string;
  currency: string;
};

export type CustomerView = {
  wa_number: string;
  name: string | null;
  address: string | null;
};

export type ChatDetail = {
  id: string;
  wa_number: string;
  name: string | null;
  human_takeover: boolean;
  needs_human: boolean;
  messages: ChatMessage[];
  files?: ConversationFile[];
  cart: CartView | null;
  customer: CustomerView;
  has_products?: boolean;
  has_qr?: boolean;
  chat_resolution?: string;
  outcome?: string | null;
  action?: string;
  payment_id?: string;
};

const KIND_FILTER = {
  all: "Todos",
  image: "Imágenes",
  audio: "Audio",
  video: "Video",
  document: "Docs",
} as const;

type KindFilter = keyof typeof KIND_FILTER;

const CLOSE_ERRORS: Record<string, string> = {
  no_products: "El pedido no tiene productos.",
  no_qr: "No hay un QR para dejar.",
  payment_locked: "Ese cobro ya está cerrado.",
  bad_action: "Esa acción no existe.",
  out_of_stock: "No hay stock para ese cobro.",
};

async function postConversation(
  id: string,
  action: "takeover" | "release" | "reply",
  body?: { text: string },
): Promise<ChatDetail> {
  const res = await fetch(`/api/backend/api/conversations/${id}/${action}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as ChatDetail;
}

async function postClose(id: string, action: string): Promise<ChatDetail> {
  const res = await fetch(`/api/backend/api/conversations/${id}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const code = typeof body.detail === "string" ? body.detail : String(res.status);
    throw new Error(code);
  }
  return (await res.json()) as ChatDetail;
}

async function postMedia(id: string, file: File, caption: string): Promise<ChatDetail> {
  const form = new FormData();
  form.append("file", file, file.name);
  if (caption) form.append("caption", caption);
  const res = await fetch(`/api/backend/api/conversations/${id}/media`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const code = typeof body.detail === "string" ? body.detail : String(res.status);
    throw new Error(code);
  }
  return (await res.json()) as ChatDetail;
}

async function postEnrichMedia(conversationId: string, mediaId: string): Promise<ChatDetail> {
  const res = await fetch(
    `/api/backend/api/conversations/${conversationId}/media/${mediaId}/enrich`,
    { method: "POST" },
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const code = typeof body.detail === "string" ? body.detail : String(res.status);
    throw new Error(code);
  }
  return (await res.json()) as ChatDetail;
}

function formatBytes(size?: number | null): string {
  if (size == null || !Number.isFinite(size) || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function FilesPanel({
  conversationId,
  files,
  onEnriched,
}: {
  conversationId: string;
  files: ConversationFile[];
  onEnriched: (detail: ChatDetail) => void;
}) {
  const [filter, setFilter] = useState<KindFilter>("all");
  const [viewer, setViewer] = useState<string | null>(null);
  const [enrichingId, setEnrichingId] = useState<string | null>(null);
  const [enrichError, setEnrichError] = useState("");
  const filtered =
    filter === "all" ? files : files.filter((item) => (item.kind || "") === filter);

  async function enrichFile(mediaId: string) {
    setEnrichingId(mediaId);
    setEnrichError("");
    try {
      const next = await postEnrichMedia(conversationId, mediaId);
      onEnriched(next);
    } catch (err) {
      setEnrichError(err instanceof Error ? err.message : "error");
    } finally {
      setEnrichingId(null);
    }
  }

  return (
    <section className={styles.ticket}>
      <h2 className={styles.kicker}>Archivos de la conversación</h2>
      <div className={styles.fileFilters}>
        {(Object.keys(KIND_FILTER) as KindFilter[]).map((key) => (
          <button
            key={key}
            type="button"
            className={filter === key ? styles.filterActive : "secondary"}
            onClick={() => setFilter(key)}
          >
            {KIND_FILTER[key]}
          </button>
        ))}
      </div>
      {enrichError ? <p className={styles.mediaError}>{enrichError}</p> : null}
      {filtered.length === 0 ? (
        <p className={styles.empty}>Sin archivos</p>
      ) : (
        <ul className={styles.fileList}>
          {filtered.map((item, index) => {
            const href =
              item.asset_id && item.status === "ready"
                ? proxyMediaUrl(`/api/media/${item.asset_id}`)
                : undefined;
            const thumb = proxyMediaUrl(item.thumb_url) || href;
            const status = (item.enrichment_status || "none").toLowerCase();
            const canEnrich =
              Boolean(item.id) &&
              item.status === "ready" &&
              (item.kind === "audio" || item.kind === "document") &&
              (status === "none" || status === "failed");
            return (
              <li key={item.id || `${item.asset_id || "x"}-${index}`} className={styles.fileRow}>
                {item.status === "failed" ? (
                  <span className={styles.mediaError}>Falló · {item.kind || "archivo"}</span>
                ) : item.status === "pending" ? (
                  <span className={styles.mediaPending}>Cargando…</span>
                ) : item.kind === "image" && href ? (
                  <button
                    type="button"
                    className={styles.mediaThumbBtn}
                    onClick={() => setViewer(href)}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated media proxy */}
                    <img className={styles.mediaThumb} src={thumb || href} alt={item.filename || "Imagen"} />
                  </button>
                ) : href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className={styles.mediaDoc}>
                    {item.filename || item.kind || "Archivo"}
                    {item.size_bytes ? (
                      <span className={styles.mediaMeta}>{formatBytes(item.size_bytes)}</span>
                    ) : null}
                  </a>
                ) : (
                  <span className={styles.empty}>{item.filename || item.kind || "Archivo"}</span>
                )}
                {item.transcript_text ? (
                  <p className={styles.enrichText}>
                    <span className={styles.enrichLabel}>Transcripción</span>
                    {item.transcript_text}
                  </p>
                ) : null}
                {item.summary_text ? (
                  <p className={styles.enrichText}>
                    <span className={styles.enrichLabel}>Resumen</span>
                    {item.summary_text}
                  </p>
                ) : null}
                {canEnrich && item.id ? (
                  <button
                    type="button"
                    className={`secondary ${styles.enrichBtn}`}
                    disabled={enrichingId === item.id}
                    onClick={() => void enrichFile(item.id!)}
                  >
                    {enrichingId === item.id ? "Procesando…" : "Transcribir / Resumir"}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <ImageViewer
        open={Boolean(viewer)}
        onClose={() => setViewer(null)}
        sources={viewer ? [viewer] : []}
        title="Archivo"
      />
    </section>
  );
}

export function ChatRoom({
  conversationId,
  initial,
}: {
  conversationId: string;
  initial: ChatDetail;
}) {
  const [detail, setDetail] = useState(initial);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const takeoverRef = useRef(initial.human_takeover);
  const pauseFlight = useRef<Promise<void> | null>(null);
  takeoverRef.current = detail.human_takeover;

  const mutate = useCallback(
    async (action: "takeover" | "release" | "reply", body?: { text: string }) => {
      const ticket = ++epoch.current;
      setPending(true);
      try {
        const next = await postConversation(conversationId, action, body);
        if (ticket === epoch.current) {
          setDetail(next);
          setError("");
        }
        return next;
      } catch (err) {
        if (ticket === epoch.current) {
          setError(err instanceof Error ? err.message : "error");
        }
        throw err;
      } finally {
        if (ticket === epoch.current) setPending(false);
      }
    },
    [conversationId],
  );

  const pauseAgent = useCallback(() => {
    if (takeoverRef.current) return;
    if (pauseFlight.current) return;
    const flight = mutate("takeover")
      .then(() => undefined)
      .catch(() => undefined)
      .finally(() => {
        pauseFlight.current = null;
      });
    pauseFlight.current = flight;
  }, [mutate]);

  const resumeAgent = useCallback(() => {
    void mutate("release").catch(() => undefined);
  }, [mutate]);

  const closeChat = useCallback(
    async (action: "wait_qr" | "paid_cash" | "no_sale" | "continue") => {
      const ticket = ++epoch.current;
      setPending(true);
      try {
        const next = await postClose(conversationId, action);
        if (ticket === epoch.current) {
          setDetail(next);
          setError("");
        }
      } catch (err) {
        if (ticket === epoch.current) {
          const code = err instanceof Error ? err.message : "";
          setError(CLOSE_ERRORS[code] || "No se pudo cerrar el chat.");
        }
      } finally {
        if (ticket === epoch.current) setPending(false);
      }
    },
    [conversationId],
  );

  const sendReply = useCallback(
    (text: string) => mutate("reply", { text }).then(() => undefined),
    [mutate],
  );

  const sendMedia = useCallback(
    async (file: File, caption: string) => {
      if (!takeoverRef.current) {
        await mutate("takeover");
      }
      const ticket = ++epoch.current;
      setPending(true);
      try {
        const next = await postMedia(conversationId, file, caption);
        if (ticket === epoch.current) {
          setDetail(next);
          setError("");
        }
      } catch (err) {
        if (ticket === epoch.current) {
          setError(err instanceof Error ? err.message : "error");
        }
        throw err;
      } finally {
        if (ticket === epoch.current) setPending(false);
      }
    },
    [conversationId, mutate],
  );

  useEffect(() => {
    let stop = false;
    async function load() {
      const ticket = epoch.current;
      try {
        const res = await fetch(`/api/backend/api/conversations/${conversationId}`, {
          cache: "no-store",
        });
        if (!res.ok || stop || ticket !== epoch.current) return;
        const data = (await res.json()) as ChatDetail;
        if (!stop && ticket === epoch.current) setDetail(data);
      } catch {
        /* el siguiente poll reintenta */
      }
    }
    load();
    const id = setInterval(load, 2000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [conversationId]);

  const customer = detail.customer ?? {
    name: detail.name,
    wa_number: detail.wa_number,
    address: null,
  };
  const lines = detail.cart?.lines ?? [];
  const discount = Number(detail.cart?.discount ?? 0);
  const showDiscount = Number.isFinite(discount) && discount > 0;

  return (
    <div className={styles.room}>
      <header className={styles.head}>
        <div>
          <h1>{detail.name || detail.wa_number}</h1>
          <p className={styles.sub}>{detail.wa_number}</p>
        </div>
        <button
          type="button"
          className={detail.human_takeover ? styles.switchPaused : `secondary ${styles.switch}`}
          aria-pressed={detail.human_takeover}
          disabled={pending}
          onClick={() => (detail.human_takeover ? resumeAgent() : pauseAgent())}
        >
          {detail.human_takeover ? "Agente pausado" : "Agente activo"}
        </button>
      </header>

      {detail.human_takeover ? (
        <div className={styles.banner} role="status">
          <span>Agente pausado</span>
          <button type="button" className="secondary" onClick={resumeAgent} disabled={pending}>
            Reanudar
          </button>
        </div>
      ) : null}

      {detail.human_takeover ? (
        <div className={styles.closeRow}>
          <button
            type="button"
            className="secondary"
            disabled={pending || detail.has_products !== true || detail.has_qr !== true}
            onClick={() => closeChat("wait_qr")}
          >
            Dejar el QR
          </button>
          <button type="button" disabled={pending} onClick={() => closeChat("paid_cash")}>
            Cobrado en efectivo
          </button>
          <button type="button" className="secondary" disabled={pending} onClick={() => closeChat("no_sale")}>
            Sin venta
          </button>
          <button type="button" className="secondary" disabled={pending} onClick={() => closeChat("continue")}>
            Seguí la venta
          </button>
        </div>
      ) : null}

      <div className={styles.stage}>
        <Thread messages={detail.messages || []} />
        <aside className={styles.context}>
          <section className={styles.ticket}>
            <div className={styles.ticketHead}>
              <h2 className={styles.kicker}>Cliente</h2>
              {detail.needs_human ? <span className="pill">Necesita humano</span> : null}
            </div>
            <dl className={styles.facts}>
              <div>
                <dt>Nombre</dt>
                <dd>{customer.name || "Sin nombre"}</dd>
              </div>
              <div>
                <dt>WhatsApp</dt>
                <dd>{customer.wa_number || detail.wa_number}</dd>
              </div>
              <div>
                <dt>Dirección</dt>
                <dd>{customer.address || "Sin dirección"}</dd>
              </div>
            </dl>
          </section>
          <section className={styles.ticket}>
            <h2 className={styles.kicker}>Carrito</h2>
            {lines.length === 0 ? (
              <p className={styles.empty}>Carrito vacío</p>
            ) : (
              <>
                <ul className={styles.lines}>
                  {lines.map((line, i) => (
                    <li key={`${line.variant_sku || line.name}-${i}`}>
                      <span>
                        {line.quantity} × {line.name}
                      </span>
                      <span className={styles.money}>
                        {line.unit_price} {line.currency}
                      </span>
                    </li>
                  ))}
                </ul>
                {showDiscount ? (
                  <p className={styles.discount}>
                    Descuento <span className={styles.money}>{detail.cart?.discount}</span>
                  </p>
                ) : null}
                <p className={styles.total}>
                  <span>Total</span>
                  <span className={styles.money}>
                    {detail.cart?.total} {detail.cart?.currency}
                  </span>
                </p>
              </>
            )}
          </section>
          <FilesPanel
            conversationId={conversationId}
            files={detail.files || []}
            onEnriched={setDetail}
          />
        </aside>
      </div>

      {error ? <p className="error">{error}</p> : null}
      <ReplyForm
        onPause={pauseAgent}
        onSend={sendReply}
        onSendMedia={sendMedia}
        canAttach={detail.human_takeover}
      />
    </div>
  );
}
