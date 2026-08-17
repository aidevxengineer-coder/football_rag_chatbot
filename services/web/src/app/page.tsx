import { AppShell } from "@/components/shell/AppShell";
import { HomeKickoff } from "@/components/chat/HomeKickoff";

export default function HomePage() {
  return (
    <AppShell showMatchStatus>
      <HomeKickoff />
    </AppShell>
  );
}
