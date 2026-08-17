import { apiJson } from "@/lib/api";

type Data<T> = { data: T };

export type LiveEvent = {
  id: string;
  competition: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  status: string;
  minute: string | null;
  started_at: string | null;
};

export type LiveEventsResponse = {
  events: LiveEvent[];
  provider: string | null;
  updated_at: string;
  message: string | null;
};

export async function getLiveEvents(): Promise<LiveEventsResponse> {
  const response = await apiJson<Data<LiveEventsResponse>>(
    "/tools/live-events",
    { cache: "no-store" },
  );
  return response.data;
}
