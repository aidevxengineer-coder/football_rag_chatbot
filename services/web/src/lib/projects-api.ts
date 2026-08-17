import { apiJson } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type Data<T> = { data: T };

export type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

export async function listProjects(): Promise<Project[]> {
  const res = await apiJson<Data<Project[]>>("/projects", {
    headers: authHeaders(),
  });
  return res.data;
}

export async function createProject(input: {
  name: string;
  description?: string | null;
}): Promise<Project> {
  const res = await apiJson<Data<Project>>("/projects", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      name: input.name,
      description: input.description || null,
    }),
  });
  return res.data;
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiJson<void>(`/projects/${projectId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}
