"use client";

import { useRef, useState } from "react";

export function ReplyForm({
  onPause,
  onSend,
  onSendMedia,
  canAttach,
}: {
  onPause: () => void;
  onSend: (text: string) => Promise<void>;
  onSendMedia?: (file: File, caption: string) => Promise<void>;
  canAttach?: boolean;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function clearFile() {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onPick(next: File | null) {
    if (preview) URL.revokeObjectURL(preview);
    setFile(next);
    if (next && next.type.startsWith("image/")) {
      setPreview(URL.createObjectURL(next));
    } else {
      setPreview(null);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (file && onSendMedia) {
        await onSendMedia(file, text.trim());
        setText("");
        clearFile();
      } else {
        const outgoing = text.trim();
        if (!outgoing) return;
        await onSend(outgoing);
        setText("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      {canAttach ? (
        <div className="actions" style={{ marginBottom: "0.5rem" }}>
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf,.doc,.docx,.xls,.xlsx,.txt"
            disabled={busy}
            onFocus={onPause}
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          />
        </div>
      ) : null}
      {file ? (
        <div style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element -- local object URL preview
            <img
              src={preview}
              alt={file.name}
              style={{ maxWidth: "12rem", maxHeight: "8rem", borderRadius: "0.4rem" }}
            />
          ) : (
            <span>
              {file.name} ({Math.round(file.size / 1024)} KB)
            </span>
          )}{" "}
          <button type="button" className="secondary" disabled={busy} onClick={clearFile}>
            Quitar
          </button>
        </div>
      ) : null}
      <textarea
        value={text}
        onFocus={onPause}
        onChange={(e) => {
          const next = e.target.value;
          if (!text.trim() && next.trim()) onPause();
          setText(next);
        }}
        placeholder={file ? "Pie o mensaje (opcional)" : "Escribí al cliente"}
        disabled={busy}
      />
      <div className="actions">
        <button type="submit" disabled={busy || (!text.trim() && !file)}>
          {file ? "Enviar archivo" : "Enviar"}
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
