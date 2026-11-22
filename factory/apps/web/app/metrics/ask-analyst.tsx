"use client";

import { useState } from "react";

import styles from "./metrics.module.css";

const NARRATIVE_PERIODS = new Set(["today", "7d", "month"]);

const SUGGESTED = [
  "¿Qué mirar primero?",
  "¿Qué repongo ya?",
  "Resumen de la semana",
] as const;

interface AnalystKpi {
  id: string;
  current: string | number | null;
}

interface AnalystFacts {
  confirmed_amount?: string;
  orders?: number;
  alert_type_count?: number;
  kpis?: AnalystKpi[];
}

interface AskBody {
  reply?: string;
  used_fallback?: boolean;
  facts?: AnalystFacts;
}

interface UsedFigure {
  label: string;
  value: string;
}

function usedFigures(facts: AnalystFacts): UsedFigure[] {
  const kpis = facts.kpis ?? [];
  const revenue = kpis.find((kpi) => kpi.id === "revenue");
  const sales = kpis.find((kpi) => kpi.id === "sales");
  const revenueText =
    revenue?.current != null ? `${revenue.current} BOB` : `${facts.confirmed_amount ?? "—"} BOB`;
  const salesText = sales?.current != null ? String(sales.current) : String(facts.orders ?? "—");
  return [
    { label: "Ingresos", value: revenueText },
    { label: "Ventas", value: salesText },
    { label: "Alertas", value: String(facts.alert_type_count ?? 0) },
  ];
}

export function AskAnalyst({ period }: { period: string }) {
  const [question, setQuestion] = useState("");
  const [reply, setReply] = useState("");
  const [figures, setFigures] = useState<UsedFigure[]>([]);
  const [usedFallback, setUsedFallback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const askedPeriod = NARRATIVE_PERIODS.has(period) ? period : "7d";

  async function ask(text: string) {
    setBusy(true);
    setError("");
    setReply("");
    setFigures([]);
    setUsedFallback(false);
    try {
      const res = await fetch("/api/backend/api/analytics/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, period: askedPeriod }),
      });
      if (!res.ok) {
        setError("No se pudo consultar al Analista.");
        return;
      }
      const body = (await res.json()) as AskBody;
      setReply(body.reply || "El Analista no devolvió texto.");
      setUsedFallback(Boolean(body.used_fallback));
      if (body.facts) setFigures(usedFigures(body.facts));
    } catch {
      setError("No se pudo consultar al Analista.");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text) {
      setError("Escribí una pregunta.");
      setReply("");
      setFigures([]);
      return;
    }
    void ask(text);
  }

  function onSuggest(text: string) {
    setQuestion(text);
    void ask(text);
  }

  return (
    <form className={styles.ask} onSubmit={onSubmit} aria-busy={busy}>
      <h2>Preguntá al Analista</h2>
      <div className={styles.suggestRow}>
        {SUGGESTED.map((text) => (
          <button
            key={text}
            type="button"
            className={styles.suggest}
            disabled={busy}
            onClick={() => onSuggest(text)}
          >
            {text}
          </button>
        ))}
      </div>
      <label>
        Pregunta
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          placeholder="¿Qué mirar primero?"
          disabled={busy}
        />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "Consultando..." : "Preguntar"}
      </button>
      <p className={styles.note}>Solo lectura. Responde con los hechos del período y no inventa números ni margen.</p>
      {busy ? <p className={styles.note}>Consultando los hechos del período…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {usedFallback && reply ? (
        <p className={styles.fallbackNote}>Respuesta sin IA: modelo no disponible</p>
      ) : null}
      {reply ? (
        <p className={styles.answer} role="status">
          {reply}
        </p>
      ) : null}
      {figures.length > 0 ? (
        <div>
          <p className={styles.factsLabel}>Cifras usadas</p>
          <ul className={styles.facts}>
            {figures.map((figure) => (
              <li key={figure.label}>
                {figure.label}: {figure.value}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  );
}
