import Link from "next/link";
import { apiGet } from "@/lib/api";
import { ChatRoom, type ChatDetail } from "./chat-room";

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let detail: ChatDetail | null = null;
  let error = "";
  try {
    detail = await apiGet<ChatDetail>(`/api/conversations/${id}`);
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  if (error || !detail) {
    return (
      <>
        <p>
          <Link href="/">← Chats</Link>
        </p>
        <p className="error">Chat no disponible ({error || "404"}).</p>
      </>
    );
  }

  return (
    <>
      <p>
        <Link href="/">← Chats</Link>
      </p>
      <ChatRoom conversationId={id} initial={detail} />
    </>
  );
}
