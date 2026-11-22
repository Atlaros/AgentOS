"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./knowledge-form.module.css";

type Branch = { name: string; hours: string; address: string; phone: string };

type Faq = { id: string; category: string; question: string; answer: string };

export type Knowledge = {
  profile?: {
    name?: string;
    summary?: string;
    audience?: string;
    hours?: string;
    contact_phone?: string;
    channels?: string[] | string;
    vision?: string[] | string;
    mission?: string[] | string;
    objectives?: string[] | string;
    branches?: Partial<Branch>[];
  };
  policies?: {
    returns?: boolean | string;
    exchanges?: boolean | string;
    cancel?: string;
    claims?: string;
    payment_window_min?: number | string;
  };
  voice?: {
    address?: string;
    tone?: string;
    traits?: string[];
    emojis?: string;
    words_use?: string[] | string;
    words_avoid?: string[] | string;
    example_replies?: string[] | string;
  };
  vocabulary?: { item?: string };
  faqs?: Partial<Faq>[];
};

const TONES = [
  { value: "cercana", label: "cercana" },
  { value: "directa", label: "directa" },
  { value: "critica", label: "crítica" },
  { value: "formal", label: "formal" },
] as const;

const EMOJI_LEVELS = [
  { value: "none", label: "Ninguno" },
  { value: "moderate", label: "Moderado" },
  { value: "many", label: "Muchos" },
] as const;

const ADDRESSES = ["tú", "usted"] as const;

function asLines(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join("\n");
  }
  return String(value ?? "").trim();
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function asChannels(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join(", ");
  }
  return String(value ?? "");
}

function yesNo(value: unknown): "yes" | "no" {
  if (value === true || value === "true" || value === "yes" || value === "si" || value === "sí") {
    return "yes";
  }
  return "no";
}

function emptyBranch(): Branch {
  return { name: "", hours: "", address: "", phone: "" };
}

export function KnowledgeForm({ initial }: { initial: Knowledge }) {
  const router = useRouter();
  const profile = initial.profile || {};
  const policies = initial.policies || {};
  const voice = initial.voice || {};
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState(profile.name || "");
  const [summary, setSummary] = useState(profile.summary || "");
  const [audience, setAudience] = useState(profile.audience || "");
  const [hours, setHours] = useState(profile.hours || "");
  const [phone, setPhone] = useState(profile.contact_phone || "");
  const [channels, setChannels] = useState(asChannels(profile.channels));
  const [vision, setVision] = useState(asLines(profile.vision));
  const [mission, setMission] = useState(asLines(profile.mission));
  const [objectives, setObjectives] = useState(asLines(profile.objectives));
  const [branches, setBranches] = useState<Branch[]>(
    (profile.branches || []).map((row) => ({
      name: row.name || "",
      hours: row.hours || "",
      address: row.address || "",
      phone: row.phone || "",
    })),
  );
  const [returns, setReturns] = useState(yesNo(policies.returns));
  const [exchanges, setExchanges] = useState(yesNo(policies.exchanges));
  const [cancel, setCancel] = useState(policies.cancel || "");
  const [claims, setClaims] = useState(policies.claims || "");
  const [paymentWindow, setPaymentWindow] = useState(
    policies.payment_window_min == null ? "" : String(policies.payment_window_min),
  );
  const [address, setAddress] = useState(voice.address || "tú");
  const [tone, setTone] = useState(voice.tone || "");
  const [emojis, setEmojis] = useState(voice.emojis || "moderate");
  const [item, setItem] = useState(initial.vocabulary?.item || "");
  const [wordsUse, setWordsUse] = useState(asLines(voice.words_use));
  const [wordsAvoid, setWordsAvoid] = useState(asLines(voice.words_avoid));
  const [examples, setExamples] = useState(asLines(voice.example_replies));

  const addressChoices = ADDRESSES.includes(address as (typeof ADDRESSES)[number])
    ? [...ADDRESSES]
    : [address, ...ADDRESSES];
  const emojiChoices = EMOJI_LEVELS.some((level) => level.value === emojis)
    ? [...EMOJI_LEVELS]
    : [{ value: emojis, label: emojis }, ...EMOJI_LEVELS];

  function patchBranch(index: number, key: keyof Branch, value: string) {
    setBranches((rows) => rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const policyPatch: {
      returns: boolean;
      exchanges: boolean;
      cancel: string;
      claims: string;
      payment_window_min?: number;
    } = {
      returns: returns === "yes",
      exchanges: exchanges === "yes",
      cancel: cancel.trim(),
      claims: claims.trim(),
    };
    if (paymentWindow.trim()) {
      const minutes = Number(paymentWindow);
      if (Number.isFinite(minutes)) policyPatch.payment_window_min = minutes;
    }
    const voicePatch: {
      address: string;
      emojis: string;
      tone?: string;
      words_use: string[];
      words_avoid: string[];
      example_replies: string[];
    } = {
      address,
      emojis,
      words_use: splitLines(wordsUse),
      words_avoid: splitLines(wordsAvoid),
      example_replies: splitLines(examples),
    };
    if (tone) voicePatch.tone = tone;
    try {
      const res = await fetch("/api/backend/api/knowledge", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: {
            name: name.trim(),
            summary: summary.trim(),
            audience: audience.trim(),
            hours: hours.trim(),
            contact_phone: phone.trim(),
            channels: channels
              .split(",")
              .map((part) => part.trim())
              .filter(Boolean),
            vision: splitLines(vision),
            mission: splitLines(mission),
            objectives: splitLines(objectives),
            branches: branches
              .map((row) => ({
                name: row.name.trim(),
                hours: row.hours.trim(),
                address: row.address.trim(),
                phone: row.phone.trim(),
              }))
              .filter((row) => Object.values(row).some(Boolean)),
          },
          policies: policyPatch,
          voice: voicePatch,
          vocabulary: { item: item.trim() },
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} autoComplete="off" aria-busy={busy}>
      <section className={styles.sheet} aria-labelledby="knowledge-identity">
        <p className={styles.kicker}>Identidad</p>
        <h2 id="knowledge-identity">Identidad del negocio</h2>
        <div className={styles.grid}>
          <label className={styles.field}>
            <span>Nombre del negocio</span>
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className={styles.field}>
            <span>Teléfono de contacto</span>
            <input value={phone} onChange={(event) => setPhone(event.target.value)} type="tel" />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Resumen</span>
            <textarea value={summary} onChange={(event) => setSummary(event.target.value)} rows={3} />
          </label>
          <label className={styles.field}>
            <span>Audiencia</span>
            <input value={audience} onChange={(event) => setAudience(event.target.value)} />
          </label>
          <label className={styles.field}>
            <span>Horario</span>
            <input value={hours} onChange={(event) => setHours(event.target.value)} />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Canales</span>
            <input
              value={channels}
              onChange={(event) => setChannels(event.target.value)}
              placeholder="WhatsApp, TikTok Live"
            />
            <span className={styles.hint}>Separados por coma.</span>
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Visión</span>
            <textarea value={vision} onChange={(event) => setVision(event.target.value)} rows={3} />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Misión</span>
            <textarea value={mission} onChange={(event) => setMission(event.target.value)} rows={3} />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Objetivos</span>
            <textarea
              value={objectives}
              onChange={(event) => setObjectives(event.target.value)}
              rows={4}
              placeholder="Un objetivo por línea"
            />
            <span className={styles.hint}>Un objetivo por línea.</span>
          </label>
        </div>

        <h3 className={styles.subhead}>Sucursales</h3>
        {branches.length === 0 ? <p className={styles.empty}>Todavía no hay sucursales.</p> : null}
        <div className={styles.stack}>
          {branches.map((branch, index) => (
            <div className={styles.block} key={`branch-${index}`}>
              <div className={styles.blockHead}>
                <span>Sucursal {index + 1}</span>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setBranches((rows) => rows.filter((_, i) => i !== index))}
                >
                  Quitar
                </button>
              </div>
              <div className={styles.grid}>
                <label className={styles.field}>
                  <span>Nombre</span>
                  <input
                    value={branch.name}
                    onChange={(event) => patchBranch(index, "name", event.target.value)}
                  />
                </label>
                <label className={styles.field}>
                  <span>Horario</span>
                  <input
                    value={branch.hours}
                    onChange={(event) => patchBranch(index, "hours", event.target.value)}
                  />
                </label>
                <label className={styles.field}>
                  <span>Dirección</span>
                  <input
                    value={branch.address}
                    onChange={(event) => patchBranch(index, "address", event.target.value)}
                  />
                </label>
                <label className={styles.field}>
                  <span>Teléfono</span>
                  <input
                    value={branch.phone}
                    onChange={(event) => patchBranch(index, "phone", event.target.value)}
                  />
                </label>
              </div>
            </div>
          ))}
        </div>
        <div className={styles.actions}>
          <button type="button" className="secondary" onClick={() => setBranches((rows) => [...rows, emptyBranch()])}>
            Agregar sucursal
          </button>
        </div>

        <h3 className={styles.subhead}>Condiciones</h3>
        <div className={styles.grid}>
          <label className={styles.field}>
            <span>Devoluciones</span>
            <select value={returns} onChange={(event) => setReturns(event.target.value as "yes" | "no")}>
              <option value="no">No</option>
              <option value="yes">Sí</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Cambios</span>
            <select value={exchanges} onChange={(event) => setExchanges(event.target.value as "yes" | "no")}>
              <option value="no">No</option>
              <option value="yes">Sí</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>Cancelación</span>
            <input value={cancel} onChange={(event) => setCancel(event.target.value)} />
          </label>
          <label className={styles.field}>
            <span>Reclamos</span>
            <input value={claims} onChange={(event) => setClaims(event.target.value)} />
          </label>
          <label className={styles.field}>
            <span>Minutos para pagar</span>
            <input
              value={paymentWindow}
              onChange={(event) => setPaymentWindow(event.target.value)}
              inputMode="numeric"
            />
          </label>
        </div>
      </section>

      <section className={styles.sheet} aria-labelledby="knowledge-voice">
        <p className={styles.kicker}>Voz</p>
        <h2 id="knowledge-voice">Cómo habla el agente</h2>
        <p className={styles.help}>
          Esto configura cómo habla Adri en esta tienda. El precio y el pago quedan fuera.
        </p>
        <div className={styles.grid}>
          <fieldset className={styles.choice}>
            <legend>Trato</legend>
            <div className={styles.options}>
              {addressChoices.map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="address"
                    value={value}
                    checked={address === value}
                    onChange={() => setAddress(value)}
                  />
                  {value}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className={`${styles.choice} ${styles.wide}`}>
            <legend>Tono</legend>
            <div className={styles.options}>
              {TONES.map((option) => (
                <label key={option.value}>
                  <input
                    type="radio"
                    name="tone"
                    value={option.value}
                    checked={tone === option.value}
                    onChange={() => setTone(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </fieldset>
          <label className={styles.field}>
            <span>Emojis</span>
            <select value={emojis} onChange={(event) => setEmojis(event.target.value)}>
              {emojiChoices.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>Cómo llama a lo que vende</span>
            <input value={item} onChange={(event) => setItem(event.target.value)} placeholder="producto" />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Palabras a usar</span>
            <textarea
              value={wordsUse}
              onChange={(event) => setWordsUse(event.target.value)}
              rows={3}
              placeholder="Una palabra o frase por línea"
            />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Palabras a evitar</span>
            <textarea
              value={wordsAvoid}
              onChange={(event) => setWordsAvoid(event.target.value)}
              rows={3}
              placeholder="Una palabra o frase por línea"
            />
          </label>
          <label className={`${styles.field} ${styles.wide}`}>
            <span>Ejemplos de respuesta</span>
            <textarea
              value={examples}
              onChange={(event) => setExamples(event.target.value)}
              rows={4}
              placeholder="Un ejemplo por línea"
            />
          </label>
        </div>
      </section>

      <div className={styles.actions}>
        <button type="submit" disabled={busy}>
          {busy ? "Guardando…" : "Guardar ficha"}
        </button>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
