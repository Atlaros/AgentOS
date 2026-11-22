"use client";

import { useEffect, useRef, useState } from "react";
import { ImageViewer } from "@/components/image-viewer";
import { proxyMediaUrl } from "@/components/media-url";
import styles from "./chat-room.module.css";
import type { ChatMessage, ChatMessageMedia } from "./chat-room";

function speakerLabel(role: string): string {
  if (role === "Humano") return "Vos";
  if (role === "customer") return "Cliente";
  const name = role.trim();
  if (!name || name === "staff") return "Agente";
  return name;
}

function bubbleKind(role: string): "customer" | "human" | "agent" {
  if (role === "customer") return "customer";
  if (role === "Humano") return "human";
  return "agent";
}

function formatBytes(size?: number | null): string {
  if (size == null || !Number.isFinite(size) || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function mediaHref(media: ChatMessageMedia): string | undefined {
  if (!media.asset_id || media.status === "failed") return undefined;
  return proxyMediaUrl(`/api/media/${media.asset_id}`);
}

function MessageMedia({ media }: { media: ChatMessageMedia }) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const href = mediaHref(media);
  const thumb = proxyMediaUrl(media.thumb_url) || href;

  if (media.status === "failed") {
    return <p className={styles.mediaError}>No se pudo cargar el archivo</p>;
  }
  if (media.status === "pending" || (!href && media.status !== "ready")) {
    return <p className={styles.mediaPending}>Archivo cargando…</p>;
  }
  if (!href) return null;

  if (media.kind === "image") {
    return (
      <>
        <button
          type="button"
          className={styles.mediaThumbBtn}
          onClick={() => setViewerOpen(true)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- authenticated media proxy */}
          <img
            className={styles.mediaThumb}
            src={thumb || href}
            alt={media.filename || "Imagen"}
          />
        </button>
        <ImageViewer
          open={viewerOpen}
          onClose={() => setViewerOpen(false)}
          sources={[href]}
          alt={media.filename || "Imagen"}
          title={media.filename || "Imagen"}
        />
      </>
    );
  }

  if (media.kind === "audio") {
    return (
      <audio className={styles.mediaPlayer} controls preload="metadata" src={href}>
        <a href={href}>Abrir audio</a>
      </audio>
    );
  }

  if (media.kind === "video") {
    return (
      <video className={styles.mediaPlayer} controls preload="metadata" src={href}>
        <a href={href}>Abrir video</a>
      </video>
    );
  }

  return (
    <a className={styles.mediaDoc} href={href} target="_blank" rel="noopener noreferrer">
      <span>{media.filename || "Documento"}</span>
      {media.size_bytes ? <span className={styles.mediaMeta}>{formatBytes(media.size_bytes)}</span> : null}
    </a>
  );
}

export function Thread({ messages }: { messages: ChatMessage[] }) {
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onScroll = () => {
      stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <div className={`messages ${styles.thread}`} ref={box}>
      {messages.map((m, i) => (
        <div
          className={`bubble ${bubbleKind(m.role)}`}
          key={`${i}-${m.role}-${m.text.slice(0, 24)}`}
        >
          <div className="who">{speakerLabel(m.role)}</div>
          {m.media ? <MessageMedia media={m.media} /> : null}
          {m.text ? <div>{m.text}</div> : null}
        </div>
      ))}
    </div>
  );
}
