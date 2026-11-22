"use client";

import { useCallback, useEffect, useState } from "react";

import { proxyMediaUrl } from "@/components/media-url";

import styles from "./orders.module.css";

export type EntityAttachment = {
  id: string;
  asset_id: string;
  filename: string;
  kind: string;
  mime: string;
  size_bytes: number;
  thumb_url?: string | null;
  url: string;
  note?: string | null;
  uploaded_by?: string | null;
  created_at?: string | null;
};

type OrderAttachmentsProps = {
  orderId: string;
  /** API path under /api/backend, e.g. /api/orders/{id}/attachments */
  apiPath: string;
  title?: string;
};

export function OrderAttachments({
  orderId,
  apiPath,
  title = "Adjuntos",
}: OrderAttachmentsProps) {
  const [rows, setRows] = useState<EntityAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend${apiPath}`, { cache: "no-store" });
      if (!res.ok) {
        setError("No se pudieron cargar los adjuntos.");
        setRows([]);
        return;
      }
      const body = (await res.json()) as { attachments?: EntityAttachment[] };
      setRows(body.attachments || []);
    } catch {
      setError("Error de red al cargar adjuntos.");
      setRows([]);
    } finally {
      setBusy(false);
    }
  }, [apiPath]);

  useEffect(() => {
    void load();
  }, [load, orderId]);

  async function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/backend${apiPath}`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: unknown };
          detail = typeof body.detail === "string" ? body.detail : "";
        } catch {
          detail = "";
        }
        const messages: Record<string, string> = {
          bad_type: "Solo se aceptan imágenes (PNG/JPEG/WebP) o PDF.",
          empty_file: "El archivo está vacío.",
          file_too_large: "El archivo es demasiado grande.",
        };
        setError(messages[detail] || "No se pudo subir el adjunto.");
        return;
      }
      const body = (await res.json()) as { attachments?: EntityAttachment[] };
      setRows(body.attachments || []);
    } catch {
      setError("Error de red al subir el adjunto.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.attachments}>
      <div className={styles.attachmentsHead}>
        <h3 className={styles.attachmentsTitle}>{title}</h3>
        <label className={styles.attachLabel}>
          <span>{busy ? "Subiendo…" : "Adjuntar archivo"}</span>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,application/pdf"
            disabled={busy}
            onChange={(event) => void onFileChange(event)}
          />
        </label>
      </div>
      <p className="meta">Imagen o PDF. No confirma pago ni cambia el estado del pedido.</p>
      {error ? <p className="error">{error}</p> : null}
      {rows.length === 0 ? (
        <p className="meta">Sin adjuntos todavía.</p>
      ) : (
        <ul className={styles.attachList}>
          {rows.map((row) => {
            const href = proxyMediaUrl(row.url);
            const thumb = proxyMediaUrl(row.thumb_url);
            return (
              <li key={row.id} className={styles.attachRow}>
                {thumb ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={thumb} alt="" className={styles.attachThumb} />
                ) : (
                  <span className={styles.attachBadge}>{row.kind === "document" ? "PDF" : "Archivo"}</span>
                )}
                <div className={styles.attachMeta}>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer">
                      {row.filename}
                    </a>
                  ) : (
                    <span>{row.filename}</span>
                  )}
                  {row.note ? <div className="meta">{row.note}</div> : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
