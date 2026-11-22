"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./knowledge-form.module.css";

type Branch = { name?: string; hours?: string; address?: string; phone?: string };

type Proposal = {
  profile?: {
    vision?: string[] | string;
    mission?: string[] | string;
    objectives?: string[] | string;
    hours?: string;
    branches?: Branch[];
  };
  policies?: Record<string, unknown>;
  faqs?: { id?: string; question?: string; answer?: string }[];
};

type ProposeResponse = {
  proposal: Proposal;
  source: { filename: string | null; chars: number };
  wrote: boolean;
};

const KINDS = [
  { value: "", label: "Auto" },
  { value: "faq", label: "FAQ" },
  { value: "identity", label: "Identidad" },
  { value: "hours", label: "Horarios" },
  { value: "policies", label: "Políticas" },
] as const;

const POLICY_LABELS: Record<string, string> = {
  returns: "Devoluciones",
  exchanges: "Cambios",
  cancel: "Cancelación",
  claims: "Reclamos",
};

function asLines(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  const text = String(value ?? "").trim();
  return text ? [text] : [];
}

function policyText(value: unknown): string {
  if (value === true) return "sí";
  if (value === false) return "no";
  return String(value ?? "").trim();
}

function hasContent(proposal: Proposal | null): proposal is Proposal {
  if (!proposal) return false;
  const profile = proposal.profile || {};
  return Boolean(
    asLines(profile.vision).length ||
      asLines(profile.mission).length ||
      asLines(profile.objectives).length ||
      (profile.hours || "").trim() ||
      (profile.branches || []).length ||
      Object.keys(proposal.policies || {}).length ||
      (proposal.faqs || []).length,
  );
}

export function DocumentPanel() {
  const router = useRouter();
  const [kind, setKind] = useState("");
  const [paste, setPaste] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState<"propose" | "save" | "">("");
  const [error, setError] = useState("");

  function clearProposal() {
    setProposal(null);
    setSource("");
  }

  async function onPropose() {
    setBusy("propose");
    setError("");
    clearProposal();
    try {
      let text = paste;
      let filename = "";
      if (file) {
        filename = file.name || "";
        if (/\.(pdf|docx?|xlsx?|pptx?|zip)$/i.test(filename)) {
          setError("Ese archivo no es texto plano. Sirve .txt, .md o .csv.");
          return;
        }
        text = await file.text();
      }
      if (!text.trim()) {
        setError("No hay texto para proponer.");
        return;
      }
      const body: { text: string; kind?: string; filename?: string } = { text };
      if (kind) body.kind = kind;
      if (filename) body.filename = filename;
      const res = await fetch("/api/backend/api/knowledge/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await res.json().catch(() => ({}))) as Partial<ProposeResponse> & {
        detail?: string;
      };
      if (!res.ok || payload.wrote) {
        if (payload.detail === "unsupported_document") {
          setError("Ese archivo no es texto plano. Sirve .txt, .md o .csv.");
        } else if (res.status === 400) {
          setError("No hay texto para proponer.");
        } else {
          setError("No se pudo proponer el documento.");
        }
        return;
      }
      setProposal(payload.proposal || {});
      const chars = payload.source?.chars ?? text.length;
      const label = payload.source?.filename || "texto pegado";
      setSource(`${label} · ${chars} caracteres. Nada se guardó.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy("");
    }
  }

  async function onConfirm() {
    if (!hasContent(proposal)) return;
    setBusy("save");
    setError("");
    try {
      const res = await fetch("/api/backend/api/knowledge", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(proposal),
      });
      if (!res.ok) throw new Error(String(res.status));
      clearProposal();
      setPaste("");
      setFile(null);
      setFileKey((value) => value + 1);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy("");
    }
  }

  function onDiscard() {
    clearProposal();
    setPaste("");
    setFile(null);
    setFileKey((value) => value + 1);
    setError("");
  }

  const profile = proposal?.profile || {};
  const vision = asLines(profile.vision);
  const mission = asLines(profile.mission);
  const objectives = asLines(profile.objectives);
  const branches = profile.branches || [];
  const policies = proposal?.policies || {};
  const faqs = proposal?.faqs || [];
  const ready = hasContent(proposal);
  const locked = busy !== "";

  return (
    <section className={`${styles.sheet} ${styles.docPanel}`} aria-labelledby="knowledge-document">
      <p className={styles.kicker}>Documento</p>
      <h2 id="knowledge-document">Proponer desde un documento</h2>
      <p className={styles.help}>
        Un .txt, .md o .csv, o el texto pegado. Proponer arma la misma ficha. La tienda no cambia
        hasta confirmar.
      </p>
      <div className={styles.grid}>
        <label className={styles.field}>
          Archivo
          <input
            key={fileKey}
            type="file"
            accept=".txt,.md,.csv,text/plain,text/markdown"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              clearProposal();
            }}
          />
        </label>
        <label className={styles.field}>
          Tipo
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            {KINDS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={`${styles.field} ${styles.wide}`}>
          Texto
          <textarea
            value={paste}
            onChange={(event) => {
              setPaste(event.target.value);
              clearProposal();
            }}
            rows={5}
            placeholder="Visión, horario, sucursales, políticas o preguntas P: / R:"
          />
        </label>
      </div>
      <div className={styles.actions}>
        <button type="button" disabled={locked} onClick={() => void onPropose()}>
          {busy === "propose" ? "Proponiendo…" : "Proponer"}
        </button>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {proposal ? (
        <div className={styles.preview} aria-live="polite">
          {source ? <p className={styles.hint}>{source}</p> : null}
          {ready ? (
            <>
              <ul className={styles.counts}>
                {vision.length ? <li>Visión {vision.length}</li> : null}
                {mission.length ? <li>Misión {mission.length}</li> : null}
                {objectives.length ? <li>Objetivos {objectives.length}</li> : null}
                {profile.hours ? <li>Horario</li> : null}
                {branches.length ? <li>Sucursales {branches.length}</li> : null}
                {Object.keys(policies).length ? <li>Políticas {Object.keys(policies).length}</li> : null}
                {faqs.length ? <li>Preguntas {faqs.length}</li> : null}
              </ul>
              {profile.hours ? <p className={styles.help}>{profile.hours}</p> : null}
              {vision.length ? <p className={styles.help}>{vision.join(" · ")}</p> : null}
              {mission.length ? <p className={styles.help}>{mission.join(" · ")}</p> : null}
              {objectives.length ? <p className={styles.help}>{objectives.join(" · ")}</p> : null}
              {branches.length ? (
                <ul className={styles.previewList}>
                  {branches.map((branch, index) => (
                    <li key={`${branch.name || "sucursal"}-${index}`} className={styles.previewItem}>
                      {branch.name || "Sucursal"}
                      <span>
                        {[branch.hours, branch.address, branch.phone].filter(Boolean).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {Object.keys(policies).length ? (
                <ul className={styles.previewList}>
                  {Object.entries(policies).map(([key, value]) => (
                    <li key={key} className={styles.previewItem}>
                      {POLICY_LABELS[key] || key}
                      <span>{policyText(value)}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {faqs.length ? (
                <ul className={styles.previewList}>
                  {faqs.slice(0, 8).map((faq) => (
                    <li key={faq.id || faq.question} className={styles.previewItem}>
                      {faq.question}
                      <span>{faq.answer}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className={styles.empty}>No encontré secciones para proponer.</p>
          )}
          <div className={styles.actions}>
            <button type="button" disabled={locked || !ready} onClick={() => void onConfirm()}>
              {busy === "save" ? "Guardando…" : "Confirmar y guardar"}
            </button>
            <button type="button" className="secondary" disabled={locked} onClick={onDiscard}>
              Descartar
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
