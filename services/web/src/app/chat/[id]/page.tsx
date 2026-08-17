import { AppShell } from "@/components/shell/AppShell";
import { ChatThread } from "@/components/chat/ChatThread";

type Props = { params: Promise<{ id: string }> };

export default async function ChatPage({ params }: Props) {
  const { id } = await params;
  return (
    <AppShell showMatchStatus>
      <ChatThread chatId={id} />
    </AppShell>
  );
}
