import { ChatList } from "./chat-list";

export default function HomePage() {
  return (
    <>
      <h1>Chats</h1>
      <p className="lead">Conversaciones del piloto Closet. Se actualizan solas.</p>
      <ChatList />
    </>
  );
}
