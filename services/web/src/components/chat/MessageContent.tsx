"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MessageContentProps = {
  content: string;
  role: string;
};

export function MessageContent({ content, role }: MessageContentProps) {
  if (!content.trim()) {
    return <p className="text-muted-foreground italic">No response generated.</p>;
  }

  if (role === "user") {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  return (
    <div className="message-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
