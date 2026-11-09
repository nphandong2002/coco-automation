import type {
  Asset, AssetKind, Capabilities, Channel, ChannelInput, ChannelSummary, Character, CharacterRole,
  CharacterVersion, ContentInput, ContentProject, Idea, Job, LogEntry, Overview, ProductionStatusInfo,
  SystemInfo, Template, ValidationReport, VersionFields, Video,
  AnalyticsFilters, AnalyticsSummary, ChannelCompare, Distribution, Insights, RetentionData, SyncQueued, SyncStatusInfo,
  Timeseries, VideoList, Monitoring, MonHistory,
  Playlist, PublishInput, PublishJob, PublishStatus, Slots, YoutubeConfig, YoutubeStatus,
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
const cp = (cid: number, pid: number) => `${ch(cid)}/content/${pid}`;
const qs = (params: Record<string, string | number | null | undefined>) => {
  const e = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return e.length ? "?" + e.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&") : "";
};
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

  // ---------------------------------------------------------------- Phase 2: assets
  assets: (p: { scope?: string; channel_id?: number | null; kind?: AssetKind | ""; q?: string } = {}) =>
    request<Asset[]>("GET", `/api/assets${qs(p)}`),
  usableAssets: (cid: number, kind?: AssetKind) => request<Asset[]>("GET", `${ch(cid)}/assets${qs({ kind })}`),
  uploadAsset: (file: File, meta: { channel_id: number | null; name: string; license_type: string; license_source: string; attribution: string; tags: string }) => {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(meta).forEach(([k, v]) => { if (v !== null && v !== "") fd.append(k, String(v)); });
    return request<Asset>("POST", "/api/assets", fd);
  },
  generateBackground: (data: { channel_id: number | null; style: string; palette?: string[] | null; seed?: number | null; name?: string }) =>
    request<Asset>("POST", "/api/assets/generate-background", data),
  updateAsset: (id: number, data: Partial<Pick<Asset, "name" | "tags" | "license_type" | "license_source" | "attribution">>) =>
    request<Asset>("PATCH", `/api/assets/${id}`, data),
  deleteAsset: (id: number) => request<void>("DELETE", `/api/assets/${id}`),

  // ---------------------------------------------------------------- Phase 2: content
  contentAll: (p: { channel_id?: number | ""; status?: string; content_type?: string; q?: string } = {}) =>
    request<ContentProject[]>("GET", `/api/content${qs(p)}`),
  channelContent: (cid: number) => request<ContentProject[]>("GET", `${ch(cid)}/content`),
  content: (cid: number, pid: number) => request<ContentProject>("GET", cp(cid, pid)),
  createContent: (cid: number, data: ContentInput) => request<ContentProject>("POST", `${ch(cid)}/content`, data),
  updateContent: (cid: number, pid: number, data: Partial<ContentInput>) => request<ContentProject>("PATCH", cp(cid, pid), data),
  deleteContent: (cid: number, pid: number) => request<void>("DELETE", cp(cid, pid)),
  validateContent: (cid: number, pid: number) => request<ValidationReport>("GET", `${cp(cid, pid)}/validate`),
  markReady: (cid: number, pid: number) => request<ContentProject>("POST", `${cp(cid, pid)}/ready`),
  syncCharacterVersion: (cid: number, pid: number) => request<ContentProject>("POST", `${cp(cid, pid)}/character/sync-version`),
  generateMetadata: (cid: number, pid: number) =>
    request<{ youtube_title: string; youtube_description: string; youtube_tags: string[] }>("POST", `${cp(cid, pid)}/metadata/generate`),
  generateThumbnail: (cid: number, pid: number) => request<ContentProject>("POST", `${cp(cid, pid)}/thumbnail/generate`),
  uploadThumbnail: (cid: number, pid: number, file: File) => request<ContentProject>("POST", `${cp(cid, pid)}/thumbnail`, upload(file)),
  removeThumbnail: (cid: number, pid: number) => request<ContentProject>("DELETE", `${cp(cid, pid)}/thumbnail`),
  render: (cid: number, pid: number, data: { job_type: "full" | "preview"; preview_seconds?: number }) =>
    request<Job>("POST", `${cp(cid, pid)}/render`, data),
  projectJobs: (cid: number, pid: number) => request<Job[]>("GET", `${cp(cid, pid)}/jobs`),
  saveAsTemplate: (cid: number, pid: number, name: string) => request<Template>("POST", `${cp(cid, pid)}/save-template`, { name }),
  templates: (channelId?: number) => request<Template[]>("GET", `/api/templates${qs({ channel_id: channelId })}`),
  deleteTemplate: (id: number) => request<void>("DELETE", `/api/templates/${id}`),
  ideas: (cid: number, status?: string) => request<Idea[]>("GET", `${ch(cid)}/ideas${qs({ status })}`),
  generateIdeas: (cid: number, count: number, content_type?: string) =>
    request<Idea[]>("POST", `${ch(cid)}/ideas/generate`, { count, ...(content_type ? { content_type } : {}) }),
  acceptIdea: (cid: number, iid: number) => request<ContentProject>("POST", `${ch(cid)}/ideas/${iid}/accept`),
  rejectIdea: (cid: number, iid: number) => request<Idea>("POST", `${ch(cid)}/ideas/${iid}/reject`),

  // ---------------------------------------------------------------- Phase 2: production
  capabilities: () => request<Capabilities>("GET", "/api/production/capabilities"),
  productionStatus: () => request<ProductionStatusInfo>("GET", "/api/production/status"),
  jobs: (p: { channel_id?: number | ""; status?: string; limit?: number } = {}) => request<Job[]>("GET", `/api/production/jobs${qs(p)}`),
  jobLog: async (id: number) => {
    const res = await fetch(`/api/production/jobs/${id}/log`);
    if (!res.ok) throw new ApiError(res.status, `Lỗi ${res.status}`);
    return res.text();
  },
  cancelJob: (id: number) => request<Job>("POST", `/api/production/jobs/${id}/cancel`),
  retryJob: (id: number) => request<Job>("POST", `/api/production/jobs/${id}/retry`),
  videos: (p: { channel_id?: number | ""; project_id?: number } = {}) => request<Video[]>("GET", `/api/production/videos${qs(p)}`),
  deleteVideo: (id: number) => request<void>("DELETE", `/api/production/videos/${id}`),

  // ---- Phase 3: YouTube + publishing
  youtubeConfig: () => request<YoutubeConfig>("GET", "/api/youtube/config"),
  youtubeStatus: (cid: number) => request<YoutubeStatus>("GET", `${ch(cid)}/youtube`),
  youtubeConnect: (cid: number) => request<{ auth_url: string }>("POST", `${ch(cid)}/youtube/connect`),
  youtubeDisconnect: (cid: number) => request<YoutubeStatus>("POST", `${ch(cid)}/youtube/disconnect`),
  playlists: (cid: number) => request<Playlist[]>("GET", `${ch(cid)}/youtube/playlists`),
  publishStatus: () => request<PublishStatus>("GET", "/api/publishing/status"),
  publishJobs: (p: { channel_id?: number | ""; status?: string; limit?: number } = {}) =>
    request<PublishJob[]>("GET", `/api/publishing/jobs${qs(p)}`),
  createPublish: (cid: number, body: PublishInput) => request<PublishJob>("POST", `${ch(cid)}/publishing/jobs`, body),
  cancelPublish: (id: number) => request<PublishJob>("POST", `/api/publishing/jobs/${id}/cancel`),
  retryPublish: (id: number) => request<PublishJob>("POST", `/api/publishing/jobs/${id}/retry`),
  // ---- Phase 5: monitoring
  monitoring: () => request<Monitoring>("GET", "/api/monitoring"),
  monitoringHistory: (hours: number) => request<MonHistory>("GET", `/api/monitoring/history?hours=${hours}`),
  runMaintenance: () => request<Record<string, number | string>>("POST", "/api/monitoring/maintenance"),
  runWatchdog: () => request<{ actions: string[] }>("POST", "/api/monitoring/watchdog"),

  // ---- Phase 4: analytics
  anSummary: (f: AnalyticsFilters) => request<AnalyticsSummary>("GET", `/api/analytics/summary${qs({ ...f })}`),
  anSeries: (f: AnalyticsFilters, granularity: string, split: boolean) =>
    request<Timeseries>("GET", `/api/analytics/timeseries${qs({ ...f, granularity, split: split ? "true" : "" })}`),
  anDistribution: (f: AnalyticsFilters, by: "channel" | "topic") =>
    request<Distribution>("GET", `/api/analytics/distribution${qs({ ...f, by })}`),
  anCompare: (f: AnalyticsFilters) => request<ChannelCompare>("GET", `/api/analytics/channels/compare${qs({ start: f.start, end: f.end })}`),
  anVideos: (f: AnalyticsFilters, sort: string) => request<VideoList>("GET", `/api/analytics/videos${qs({ ...f, sort, limit: 200 })}`),
  anInsights: (f: AnalyticsFilters) => request<Insights>("GET", `/api/analytics/insights${qs({ ...f })}`),
  anVideoRetention: (videoId: number) => request<RetentionData>("GET", `/api/analytics/videos/${videoId}/retention`),
  anChannelRetention: (channelId?: number | "") => request<RetentionData>("GET", `/api/analytics/retention${qs({ channel_id: channelId })}`),
  anSyncStatus: (channelId?: number | "") => request<SyncStatusInfo>("GET", `/api/analytics/sync${qs({ channel_id: channelId })}`),
  anSyncAll: () => request<SyncQueued>("POST", "/api/analytics/sync"),
  anSyncChannel: (cid: number, backfillDays?: number) =>
    request<{ queued: boolean; message: string }>("POST", `${ch(cid)}/analytics/sync${qs({ backfill_days: backfillDays })}`),

  slots: (cid: number, count = 5) => request<Slots>("GET", `${ch(cid)}/publishing/slots${qs({ count })}`),
};
