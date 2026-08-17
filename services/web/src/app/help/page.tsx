import { AppShell } from "@/components/shell/AppShell";

const guides = [
  {
    icon: "sports",
    title: "Kickoff",
    copy: "Start a standalone match thread and ask a tactical question. Guest threads are saved locally and merge into your account after sign-in.",
  },
  {
    icon: "emoji_events",
    title: "Leagues",
    copy: "Organize recurring research and briefings as leagues. Chats can remain standalone and do not require a league.",
  },
  {
    icon: "library_add",
    title: "Ball Knowledge",
    copy: "Upload your own reports and notes. Indexed documents ground answers across your account’s chats.",
  },
  {
    icon: "sensors",
    title: "Live Events",
    copy: "Follow live scores from the configured football MCP provider. The feed refreshes automatically every minute.",
  },
];

export default function HelpPage() {
  return (
    <AppShell>
      <div className="h-full overflow-y-auto px-6 py-10 md:px-10">
        <div className="mx-auto max-w-4xl">
          <p className="font-mono text-xs uppercase tracking-widest text-primary">
            Matchday manual
          </p>
          <h1 className="mt-2 font-serif text-3xl font-bold">Help</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Pitchside combines your football knowledge with live tools and a
            staged analysis pipeline.
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {guides.map((guide) => (
              <article
                key={guide.title}
                className="rounded-xl border border-border bg-card p-5"
              >
                <span className="material-symbols-outlined text-2xl text-primary">
                  {guide.icon}
                </span>
                <h2 className="mt-3 font-serif text-lg font-semibold">
                  {guide.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {guide.copy}
                </p>
              </article>
            ))}
          </div>

          <section className="mt-8 rounded-xl border border-border bg-muted/40 p-5">
            <h2 className="font-serif text-lg font-semibold">Quick tips</h2>
            <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
              <li>• Enable web search in the composer only when current sources are needed.</li>
              <li>• Watch Match Status to follow retrieval, tools, drafting, and judging.</li>
              <li>• Settings is signed-in only; restart services after changing provider keys.</li>
              <li>• AI analysis can be wrong—verify critical scores and match facts.</li>
            </ul>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
