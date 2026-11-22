"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import styles from "./knowledge-form.module.css";

const FAQ_REPLACE_ID = "__faq_list_replaces__";

export type FaqInput = {
  id?: string;
  category?: string;
  question?: string;
  answer?: string;
};

type Faq = { id: string; category: string; question: string; answer: string };

type Draft = { id: string; category: string; question: string; answer: string };

const emptyDraft: Draft = { id: "", category: "", question: "", answer: "" };

function normalize(rows: FaqInput[] | undefined): Faq[] {
  return (rows || [])
    .filter((row) => (row.id || "") !== FAQ_REPLACE_ID)
    .map((row, index) => ({
      id: (row.id || "").trim() || `faq-${index + 1}`,
      category: (row.category || "").trim(),
      question: (row.question || "").trim(),
      answer: (row.answer || "").trim(),
    }));
}

function slugFromQuestion(question: string): string {
  return question
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function uniqueFaqId(question: string, rows: Faq[]): string {
  const used = new Set(rows.map((row) => row.id));
  const slug = slugFromQuestion(question);
  if (slug && slug !== FAQ_REPLACE_ID && !used.has(slug)) return slug;
  let n = rows.length + 1;
  let id = `faq-${n}`;
  while (used.has(id) || id === FAQ_REPLACE_ID) {
    n += 1;
    id = `faq-${n}`;
  }
  return id;
}

function preview(answer: string): string {
  const text = answer.replace(/\s+/g, " ").trim();
  if (text.length <= 140) return text;
  const clipped = text.slice(0, 140).trimEnd();
  return `${clipped}…`;
}

function countLabel(count: number): string {
  if (count === 1) return "1 pregunta guardada.";
  return `${count} preguntas guardadas.`;
}

export function FaqPanel({ initial }: { initial: FaqInput[] }) {
  const router = useRouter();
  const questionRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Faq[]>(() => normalize(initial));
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [removingId, setRemovingId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (draft.id) questionRef.current?.focus();
  }, [draft.id]);

  async function putFaqs(faqs: FaqInput[]) {
    const res = await fetch("/api/backend/api/knowledge", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ faqs }),
    });
    if (!res.ok) throw new Error(String(res.status));
  }

  async function onSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.question.trim();
    const answer = draft.answer.trim();
    if (!question || !answer) return;
    const id = draft.id || uniqueFaqId(question, rows);
    setBusy(true);
    setError("");
    try {
      const saved = {
        id,
        category: draft.category.trim(),
        question,
        answer,
      };
      await putFaqs([saved]);
      setRows((current) => {
        const index = current.findIndex((row) => row.id === id);
        if (index === -1) return [...current, saved];
        return current.map((row) => (row.id === id ? saved : row));
      });
      setDraft(emptyDraft);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  async function removeFaq(id: string) {
    setRemovingId(id);
    setError("");
    const remaining = rows.filter((row) => row.id !== id);
    try {
      await putFaqs([{ id: FAQ_REPLACE_ID, category: "", question: "", answer: "" }, ...remaining]);
      if (draft.id === id) setDraft(emptyDraft);
      setRows(remaining);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setRemovingId("");
    }
  }

  const locked = busy || removingId !== "";
  const editing = draft.id !== "";

  return (
    <section className={`${styles.sheet} ${styles.faqPanel}`} aria-labelledby="knowledge-faqs">
      <p className={styles.kicker}>Preguntas</p>
      <h2 id="knowledge-faqs">Preguntas frecuentes</h2>
      <p className={styles.help}>
        {rows.length === 0
          ? "Todavía no hay preguntas frecuentes. La primera se carga abajo."
          : `${countLabel(rows.length)} Cada una se guarda sola, sin reescribir la ficha.`}
      </p>

      <div className={styles.faqList}>
        {rows.map((faq) => {
          const active = draft.id === faq.id;
          return (
            <article
              key={faq.id}
              className={active ? `${styles.faqItem} ${styles.faqItemActive}` : styles.faqItem}
            >
              <div className={styles.faqBody}>
                {faq.category ? <p className={styles.faqCategory}>{faq.category}</p> : null}
                <h3 className={styles.faqQuestion}>{faq.question || "Sin pregunta"}</h3>
                {faq.answer ? <p className={styles.faqPreview}>{preview(faq.answer)}</p> : null}
              </div>
              <div className={styles.faqTools}>
                <button
                  type="button"
                  className="secondary"
                  aria-pressed={active}
                  disabled={locked}
                  onClick={() =>
                    setDraft({
                      id: faq.id,
                      category: faq.category,
                      question: faq.question,
                      answer: faq.answer,
                    })
                  }
                >
                  Editar
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={locked}
                  onClick={() => removeFaq(faq.id)}
                >
                  {removingId === faq.id ? "Quitando…" : "Quitar"}
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <form className={styles.faqEditor} onSubmit={onSave} autoComplete="off" aria-busy={busy}>
        <h3 className={styles.subhead}>{editing ? "Editar pregunta" : "Nueva pregunta"}</h3>
        <div className={styles.grid}>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Categoría</span>
            <input
              value={draft.category}
              onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
              placeholder="Opcional"
            />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Pregunta</span>
            <input
              ref={questionRef}
              value={draft.question}
              onChange={(event) => setDraft((current) => ({ ...current, question: event.target.value }))}
              required
            />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Respuesta</span>
            <textarea
              value={draft.answer}
              onChange={(event) => setDraft((current) => ({ ...current, answer: event.target.value }))}
              rows={3}
              required
            />
          </label>
        </div>
        <div className={styles.actions}>
          <button type="submit" disabled={locked}>
            {busy ? "Guardando…" : "Guardar pregunta"}
          </button>
          {editing ? (
            <button type="button" className="secondary" disabled={locked} onClick={() => setDraft(emptyDraft)}>
              Cancelar
            </button>
          ) : null}
          {error ? (
            <p className="error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      </form>
    </section>
  );
}
