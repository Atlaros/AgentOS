import { apiGet } from "@/lib/api";
import { DocumentPanel } from "./document-panel";
import { FaqPanel } from "./faq-panel";
import { KnowledgeForm, type Knowledge } from "./knowledge-form";

export default async function KnowledgePage() {
  let data: Knowledge | null = null;
  let error = "";
  try {
    data = await apiGet<Knowledge>("/api/knowledge");
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  const revision = data ? JSON.stringify(data) : "";

  return (
    <>
      <h1>Conocimiento</h1>
      <p className="lead">
        Identidad del negocio y estilo del agente. Las preguntas frecuentes se listan y se guardan
        de a una. Un documento propone la estructura y solo se escribe al confirmar. El precio, el
        stock y el pago no se editan aquí.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {data ? (
        <>
          <FaqPanel key={`${revision}-faqs`} initial={data.faqs || []} />
          <DocumentPanel />
          <KnowledgeForm key={revision} initial={data} />
        </>
      ) : null}
    </>
  );
}
