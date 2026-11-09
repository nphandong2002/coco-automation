import type {
  Channel, ChannelInput, ChannelSummary, Character, CharacterRole, CharacterVersion,
  LogEntry, Overview, SystemInfo, VersionFields,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "Không kết nối được tới server");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? `Lỗi ${res.status}`);
  return data as T;
}

const ch = (id: number) => `/api/channels/${id}`;
const chr = (cid: number, id: number) => `${ch(cid)}/characters/${id}`;

function upload(file: File, extra: Record<string, string> = {}): FormData {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  return fd;
}

export const api = {
  overview: () => request<Overview>("GET", "/api/overview"),
  systemInfo: () => request<SystemInfo>("GET", "/api/system/info"),
  logs: (limit = 100) => request<LogEntry[]>("GET", `/api/system/logs?limit=${limit}`),

  channels: () => request<Channel[]>("GET", "/api/channels"),
  channel: (id: number) => request<Channel>("GET", ch(id)),
  channelSummary: (id: number) => request<ChannelSummary>("GET", `${ch(id)}/summary`),
  channelActivity: (id: number) => request<LogEntry[]>("GET", `${ch(id)}/activity`),
  createChannel: (data: ChannelInput) => request<Channel>("POST", "/api/channels", data),
  updateChannel: (id: number, data: Partial<ChannelInput>) => request<Channel>("PATCH", ch(id), data),
  deleteChannel: (id: number, confirm: string) =>
    request<void>("DELETE", `${ch(id)}?confirm=${encodeURIComponent(confirm)}`),
  enableChannel: (id: number) => request<Channel>("POST", `${ch(id)}/enable`),
  pauseChannel: (id: number) => request<Channel>("POST", `${ch(id)}/pause`),
  clearChannelError: (id: number) => request<Channel>("POST", `${ch(id)}/clear-error`),
  cloneChannel: (id: number, data: { name: string; code: string; include_characters: boolean }) =>
    request<Channel>("POST", `${ch(id)}/clone`, data),
  uploadChannelImage: (id: number, kind: "avatar" | "banner", file: File) =>
    request<Channel>("POST", `${ch(id)}/${kind}`, upload(file)),

  allCharacters: () => request<Character[]>("GET", "/api/characters"),
  characters: (cid: number) => request<Character[]>("GET", `${ch(cid)}/characters`),
  character: (cid: number, id: number) => request<Character>("GET", chr(cid, id)),
  createCharacter: (cid: number, data: VersionFields & { name: string; species: string; role: CharacterRole }) =>
    request<Character>("POST", `${ch(cid)}/characters`, data),
  updateCharacter: (cid: number, id: number, data: { name?: string; species?: string; archived?: boolean }) =>
    request<Character>("PATCH", chr(cid, id), data),
  deleteCharacter: (cid: number, id: number) => request<void>("DELETE", chr(cid, id)),
  setRole: (cid: number, id: number, role: CharacterRole) => request<Character>("PUT", `${chr(cid, id)}/role`, { role }),
  versions: (cid: number, id: number) => request<CharacterVersion[]>("GET", `${chr(cid, id)}/versions`),
  createVersion: (cid: number, id: number, data: VersionFields & { change_note: string }) =>
    request<Character>("POST", `${chr(cid, id)}/versions`, data),
  activateVersion: (cid: number, id: number, vid: number) =>
    request<Character>("POST", `${chr(cid, id)}/versions/${vid}/activate`),
  uploadCharacterImage: (cid: number, id: number, slot: string, file: File, expressionName?: string) =>
    request<Character>("POST", `${chr(cid, id)}/images`,
      upload(file, { slot, ...(expressionName ? { expression_name: expressionName } : {}) })),
  removeCharacterImage: (cid: number, id: number, slot: string, key: string) =>
    request<Character>("DELETE", `${chr(cid, id)}/images?slot=${slot}&key=${encodeURIComponent(key)}`),
  grant: (cid: number, id: number, target: number, role: CharacterRole) =>
    request<Character>("POST", `${chr(cid, id)}/grants`, { target_channel_id: target, role }),
  revoke: (cid: number, id: number, target: number) =>
    request<Character>("DELETE", `${chr(cid, id)}/grants/${target}`),
};
