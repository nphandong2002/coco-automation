export type ChannelStatus = "active" | "paused" | "error" | "disconnected";
export type CharacterRole = "primary" | "secondary";

export interface ScheduleSlot { weekday: number; time: string }
export interface PublishSchedule { timezone: string; slots: ScheduleSlot[] }
export interface VisualStyle { theme: string; mood: string; palette: string[]; keywords: string[] }
export interface AudioStyle { ambience: string[]; music: string; notes: string }

export interface Channel {
  id: number;
  code: string;
  name: string;
  description: string;
  language: string;
  target_country: string;
  topics: string[];
  visual_style: Partial<VisualStyle>;
  audio_style: Partial<AudioStyle>;
  publish_schedule: Partial<PublishSchedule>;
  status: ChannelStatus;
  enabled: boolean;
  last_error: string | null;
  last_error_at: string | null;
  youtube_connected: boolean;
  youtube_channel_title: string | null;
  avatar_url: string | null;
  banner_url: string | null;
  cloned_from_id: number | null;
  character_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChannelInput {
  code?: string;
  name: string;
  description: string;
  language: string;
  target_country: string;
  topics: string[];
  visual_style: VisualStyle;
  audio_style: AudioStyle;
  publish_schedule: PublishSchedule;
}

export interface ChannelSummary {
  characters_owned: number;
  characters_granted: number;
  content_projects: number;
  videos: number;
  render_jobs_active: number;
  publishing_jobs_pending: number;
  analytics_days_synced: number;
}

export interface Expression { name: string; image: string; image_url: string }

export interface CharacterVersion {
  id: number;
  version_no: number;
  appearance: string;
  art_style: string;
  primary_colors: string[];
  outfit: string;
  personality: string;
  usual_settings: string[];
  allowed_animations: string[];
  expressions: Expression[];
  avatar_url: string | null;
  full_body_url: string | null;
  reference_images: { path: string; url: string }[];
  change_note: string;
  created_at: string;
  is_current: boolean;
}

export interface ShareInfo { channel_id: number; channel_name: string; role: CharacterRole; granted_at: string }

export interface Character {
  id: number;
  name: string;
  species: string;
  archived: boolean;
  owner_channel_id: number;
  owner_channel_name: string;
  channel_id: number;
  role: CharacterRole;
  is_owner: boolean;
  version_count: number;
  current_version: CharacterVersion | null;
  shared_with: ShareInfo[];
  created_at: string;
  updated_at: string;
}

export interface VersionFields {
  appearance?: string;
  art_style?: string;
  primary_colors?: string[];
  outfit?: string;
  personality?: string;
  usual_settings?: string[];
  allowed_animations?: string[];
}

export interface LogEntry {
  id: number;
  created_at: string;
  level: string;
  category: string;
  channel_id: number | null;
  channel_name: string | null;
  message: string;
}

export interface MetricValue { value: number | null; source: "youtube_api" | "estimated" | "not_synced"; synced_at: string | null }

export interface Overview {
  channels_total: number;
  channels_by_status: Record<ChannelStatus, number>;
  characters_total: number;
  content_projects_total: number;
  videos_produced: number;
  render_jobs_running: number;
  render_jobs_queued: number;
  videos_waiting_publish: number;
  total_views: MetricValue;
  total_subscribers: MetricValue;
  total_subscribers_gained: MetricValue;
  total_watch_time_minutes: MetricValue;
  daily_views: { day: string; views: number }[];
  recent_activity: LogEntry[];
}

export interface SystemInfo {
  app_version: string;
  database_ok: boolean;
  database_message: string;
  migration_revision: string | null;
  ffmpeg_path: string | null;
  storage_dir: string;
  disk_total_gb: number;
  disk_free_gb: number;
  cpu_percent: number;
  ram_total_gb: number;
  ram_used_percent: number;
  secret_key_configured: boolean;
  dashboard_auth_enabled: boolean;
}

// ------------------------------------------------------------------ Phase 2
export type AssetKind = "image" | "audio" | "video" | "font" | "model";
export type LicenseType = "owned" | "cc0" | "cc_by" | "royalty_free" | "licensed";
export type ContentType =
  | "study_with_me" | "pomodoro" | "cozy_ambience" | "rain_sounds" | "fireplace_sounds"
  | "sleep_ambience" | "reading_room" | "cafe_ambience" | "nature_ambience";
export type ProductionStatus = "draft" | "ready" | "queued" | "rendering" | "rendered" | "failed" | "published";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Asset {
  id: number;
  channel_id: number | null;
  channel_name: string | null;
  kind: AssetKind;
  name: string;
  url: string;
  sha256: string;
  size_bytes: number;
  mime_type: string;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  license_type: LicenseType;
  license_source: string;
  attribution: string;
  tags: string[];
  source: "upload" | "generated";
  meta: Record<string, unknown>;
  created_at: string;
}

export interface CharacterPlacement { position: string; scale: number; motion: string }
export interface AnimationConfig { background_motion: string; effects: string[]; character: CharacterPlacement }
export interface AudioLayer { kind: "asset" | "generator"; asset_id?: number | null; generator?: string | null; volume: number }
export interface PomodoroConfig { focus_min: number; short_break_min: number; long_break_min: number; cycles_before_long: number }
export interface OverlayConfig { mode: string; position: string; color: string; box: boolean; font_asset_id: number | null; labels: Record<string, string> }
export interface RenderSettings {
  overlay: OverlayConfig; chime: boolean; chime_volume: number; master_volume: number;
  resolution: string; fps: number; crf: number | null; preset: string | null;
}

export interface JobBrief {
  id: number; job_type: string; status: JobStatus; progress: number; step: string;
  error: string | null; created_at: string; finished_at: string | null; output_url: string | null;
}

export interface ContentProject {
  id: number;
  channel_id: number;
  channel_name: string;
  title: string;
  content_type: ContentType;
  character_id: number | null;
  character_name: string | null;
  character_version_id: number | null;
  character_version_no: number | null;
  character_current_version_id: number | null;
  theme: string;
  script: string;
  setting: string;
  background_asset_id: number | null;
  background_url: string | null;
  animation: AnimationConfig;
  scene3d: import("../scene3d/types").Scene3D | null;
  scene3d_model_url: string | null;
  audio_layers: AudioLayer[];
  duration_minutes: number;
  pomodoro: PomodoroConfig | null;
  render_settings: RenderSettings;
  youtube_title: string;
  youtube_description: string;
  youtube_tags: string[];
  thumbnail_url: string | null;
  status: ProductionStatus;
  last_error: string | null;
  template_id: number | null;
  idea_id: number | null;
  fingerprint: string | null;
  video_count: number;
  latest_job: JobBrief | null;
  created_at: string;
  updated_at: string;
}

export interface ContentInput {
  scene3d?: import("../scene3d/types").Scene3D;
  clear_scene3d?: boolean;
  title: string;
  content_type: ContentType;
  character_id?: number | null;
  clear_character?: boolean;
  theme?: string;
  script?: string;
  setting?: string;
  background_asset_id?: number | null;
  clear_background?: boolean;
  animation?: AnimationConfig;
  audio_layers?: AudioLayer[];
  duration_minutes?: number;
  pomodoro?: PomodoroConfig | null;
  clear_pomodoro?: boolean;
  render_settings?: RenderSettings;
  youtube_title?: string;
  youtube_description?: string;
  youtube_tags?: string[];
  template_id?: number | null;
  idea_id?: number | null;
}

export interface ValidationReport { ok: boolean; errors: string[]; warnings: string[] }

export interface Template { id: number; channel_id: number | null; name: string; content_type: ContentType; config: Record<string, any>; builtin: boolean }

export interface Idea {
  id: number; channel_id: number; title: string; content_type: ContentType; theme: string;
  description: string; attributes: Record<string, any>; status: "new" | "accepted" | "rejected" | "used"; created_at: string;
}

export interface Job {
  id: number;
  channel_id: number;
  channel_name: string;
  content_project_id: number;
  project_title: string | null;
  job_type: "full" | "preview";
  status: JobStatus;
  step: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  priority: number;
  worker_id: string | null;
  heartbeat_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  duration_sec: number | null;
  timeout_sec: number;
  cancel_requested: boolean;
  error: string | null;
  output_url: string | null;
  video_id: number | null;
  eta_seconds: number | null;
  has_log: boolean;
}

export interface QcCheck { name: string; ok: boolean; detail: string; critical: boolean }

export interface Video {
  id: number;
  channel_id: number;
  channel_name: string;
  content_project_id: number | null;
  video_job_id: number | null;
  title: string;
  url: string;
  thumbnail_url: string | null;
  duration_sec: number;
  width: number;
  height: number;
  fps: number;
  size_bytes: number;
  sha256: string | null;
  qc_passed: boolean;
  qc_report: { passed?: boolean; checks?: QcCheck[]; render_seconds?: number };
  youtube_video_id: string | null;
  privacy_status: string | null;
  created_at: string;
}

export interface WorkerInfo {
  worker_id: string; kind: string; hostname: string; pid: number; state: string; online: boolean;
  current_job_id: number | null; started_at: string; heartbeat_at: string; info: Record<string, any>;
}

export interface ProductionStatusInfo { workers: WorkerInfo[]; queued: number; running: number; failed_24h: number; succeeded_24h: number }

export interface Capabilities {
  scene3d?: { available: boolean; chromium: string | null; playwright: boolean; frontend_built: boolean; reason: string | null } | null;
  ffmpeg_path: string | null;
  ffmpeg_version: string | null;
  ffprobe_path: string | null;
  drawtext: boolean;
  font_path: string | null;
  render_threads: number;
  render_preset: string;
  render_crf: number;
  loop_seconds: number;
  durations: number[];
  preview_seconds: number[];
  generators: Record<string, { label: string; description: string }>;
  background_motions: Record<string, string>;
  effects: Record<string, string>;
  character_motions: Record<string, string>;
  character_positions: string[];
  overlay_modes: Record<string, string>;
  overlay_positions: string[];
  background_styles: Record<string, string>;
  resolutions: string[];
  x264_presets: string[];
}

// ---------------------------------------------------------------- Phase 3: YouTube / publishing
export interface YoutubeStatus {
  configured: boolean; connected: boolean; status: "valid" | "expired" | "revoked" | "disconnected";
  youtube_channel_id: string | null; youtube_channel_title: string | null; google_account_email: string | null;
  scopes: string[]; token_expiry: string | null; last_refresh_at: string | null; last_error: string | null;
}
export interface YoutubeConfig { configured: boolean; redirect_uri: string; scopes: string[] }
export interface Playlist { id: string; title: string; privacy: string | null }
export type PrivacyStatus = "private" | "unlisted" | "public";
export interface PublishHistoryEntry { at: string; event: string; detail: string }
export interface PublishJob {
  id: number; channel_id: number; channel_name: string; video_id: number; video_title: string | null;
  thumbnail_url: string | null; status: JobStatus; privacy_status: PrivacyStatus; publish_at: string | null;
  title: string; description: string; tags: string[]; playlist_id: string | null; category_id: string;
  bytes_uploaded: number; size_bytes: number | null; progress: number | null; attempts: number; max_attempts: number;
  next_attempt_at: string | null; youtube_video_id: string | null; youtube_url: string | null;
  uploaded_at: string | null; last_error: string | null; history: PublishHistoryEntry[]; created_at: string;
}
export interface PublishInput {
  video_id: number; title?: string; description?: string; tags?: string[]; privacy: PrivacyStatus;
  publish_at?: string | null; use_next_slot?: boolean; playlist_id?: string | null; category_id?: string;
}
export interface Slots { timezone: string; slots: string[] }
export interface PublishStatus { counts: Record<string, number>; workers: WorkerInfo[] }

// ---------------------------------------------------------------- Phase 4: analytics
export type DataState = "synced" | "not_synced";
export interface Kpi { value: number | null; previous: number | null; change_pct: number | null; source: "youtube_api" | "not_synced" }
export type KpiKey = "views" | "watch_time_minutes" | "average_view_duration_sec" | "average_view_percentage"
  | "subscribers_gained" | "subscribers_lost" | "subscribers_net" | "likes" | "comments";
export interface AnalyticsFilters { channel_id?: number | ""; start?: string; end?: string; topic?: string; video_status?: string }

export interface VideoPerf {
  video_id: number; channel_id: number; channel_name: string; title: string; youtube_video_id: string;
  published_at: string | null; privacy_status: string | null; duration_minutes: number | null;
  content_type: ContentType | null; theme: string; has_data: boolean; data_state: DataState; synced_at: string | null;
  views: number | null; watch_time_minutes: number | null; average_view_duration_sec: number | null;
  average_view_percentage: number | null; subscribers_gained: number | null; likes: number | null; comments: number | null;
  engagement_rate: number | null; views_per_day: number | null; retention_avg: number | null; has_retention: boolean;
  score: number | null; label: "strong" | "average" | "weak" | "insufficient_data" | "too_new" | "not_synced";
  weak_reasons: string[]; components: Record<string, number>; exposure_days: number;
}
export interface AnalyticsSummary {
  range: { start: string; end: string; days: number };
  filters: { channel_id: number | null; topic: string | null; video_status: string | null };
  basis: "channel" | "videos"; data_state: DataState; preliminary_since: string; last_synced_at: string | null;
  kpis: Record<KpiKey, Kpi>;
  subscribers_total: { value: number | null; source: string; synced_at: string | null; channels_counted: number; channels_total: number; channels_hidden: number };
  production: { videos_published: number; videos_processing: number; videos_failed: number };
  top_video: VideoPerf | null;
  best_channel: { channel_id: number; channel_name: string; basis: string; watch_time_minutes: number; views: number } | null;
  sync: { connected: number; synced: number; not_synced: number; errors: { channel_id: number; channel_name: string; kind: string | null; error: string | null }[] };
}
export interface SeriesPoint { period: string; views: number; watch_time_minutes: number; subscribers_net: number; likes: number; comments: number; preliminary: boolean }
export interface Timeseries {
  basis: string; granularity: string; data_state: DataState; preliminary_since: string; points: SeriesPoint[];
  by_channel: { channel_id: number; channel_name: string; points: SeriesPoint[] }[];
}
export interface ChannelCompareRow {
  channel_id: number; channel_name: string; enabled: boolean; data_state: string; source: string;
  views: number | null; watch_time_minutes: number | null; subscribers_net: number | null; engagement_rate: number | null;
  average_view_percentage: number | null; videos_published: number; views_growth_pct: number | null;
  watch_time_growth_pct: number | null; subscribers_total: number | null; subscribers_growth_pct: number | null;
}
export interface ChannelCompare { best: AnalyticsSummary["best_channel"]; growth_note: string; items: ChannelCompareRow[] }
export interface Distribution { by: string; total_views: number | null; data_state: DataState; items: { key: string; label: string; views: number; share: number | null }[] }
export interface VideoList { items: VideoPerf[]; total: number; scoring: { weights: Record<string, number>; note: string } }
export interface RetentionSummary { average: number | null; at_10: number | null; at_25: number | null; at_50: number | null; at_75: number | null; steepest_drop: { from: number; to: number; delta: number } | null }
export interface RetentionData { data_state: DataState; points: [number, number][]; summary: RetentionSummary; n_videos?: number; title?: string; note?: string; synced_at?: string | null }
export interface GroupStat { group: string; key: string | number; label: string; minutes?: number; n_videos: number; n_scored: number; total_views: number; avg_views_per_day: number | null; avg_view_pct: number | null; subs_per_1k_views: number | null; avg_score: number | null }
export interface SlotStat { hour?: number; weekday?: number; n: number; avg_views_7d: number | null; avg_watch_minutes_7d: number | null; reliable: boolean }
export interface Recommendation { kind: string; confidence: "low" | "medium" | "high"; text: string; evidence: Record<string, unknown>; suggested_content_type?: ContentType | null }
export interface Insights {
  videos_total: number; videos_scored: number; topics: GroupStat[]; themes: GroupStat[]; durations: GroupStat[];
  posting_times: { measured_videos: number; by_hour: SlotStat[]; by_weekday: SlotStat[]; note: string };
  underperformers: { video_id: number; title: string; channel_name: string; score: number | null; reasons: string[] }[];
  retention: { n_videos: number; summary: RetentionSummary }; recommendations: Recommendation[];
}
export interface SyncChannel {
  channel_id: number; channel_name: string; enabled: boolean; connected: boolean;
  state: "synced" | "stale" | "not_synced" | "error" | "disconnected"; last_success_at: string | null;
  last_attempt_at: string | null; synced_through: string | null; videos_synced: number; videos_failed: number;
  error_kind: string | null; error: string | null; retry_after: string | null;
}
export interface SyncStatusInfo { channels: SyncChannel[]; worker_alive: boolean; interval_minutes: number }
export interface SyncQueued { queued: number; results: { channel_id: number; queued: boolean; message: string }[] }

// ---------------------------------------------------------------- Phase 5: monitoring
export interface MonAlert { severity: "warning" | "critical"; code: string; message: string; hint: string }
export interface MonWorker { kind: string; online: boolean; state: string; worker_id: string | null; pid: number | null; current_job_id: number | null; heartbeat_age_sec: number | null; started_at: string | null }
export interface QueueStat { queued: number; running: number; failed_24h?: number; succeeded_24h?: number; waiting_retry?: number; oldest_queued_sec?: number | null }
export interface Monitoring {
  generated_at: string; hostname: string; status: "ok" | "warning" | "critical";
  host: { cpu_percent: number; cpu_count: number; load_avg: number[] | null; ram_total_gb: number; ram_percent: number; ram_available_mb: number; swap_percent: number | null; disk_total_gb: number; disk_free_gb: number; disk_percent: number; storage_dir: string; uptime_hours: number };
  processes: { ffmpeg: { pid: number; rss_mb: number; elapsed_sec: number; cmd: string }[]; ffmpeg_rss_mb: number; app_processes: number; app_rss_mb: number };
  workers: MonWorker[];
  queues: { render: QueueStat; upload: QueueStat; analytics: QueueStat };
  youtube: {
    credentials: { valid: number; expired: number; revoked: number };
    errors_24h: { category: string; level: string; count: number; last_at: string }[];
    recent_errors: { at: string; category: string; level: string; message: string; channel_id: number | null }[];
    sync_errors: { channel_id: number; channel_name: string; kind: string | null; error: string; retry_after: string | null }[];
    quota_parked: number;
  };
  database: { ok: boolean; message: string; latency_ms?: number; size_mb?: number; connections?: number };
  stalled: { kind: string; job_id: number; channel_id: number | null; age_sec: number; reason: string }[];
  alerts: MonAlert[];
  config: { secret_key_configured: boolean; ffmpeg_path: string | null; dashboard_auth_enabled: boolean; app_version: string; limits: Record<string, number> };
}
export interface MonHistory { hours: number; interval_seconds: number; points: { ts: string; cpu: number; ram: number; ram_available_mb: number; disk_free_gb: number; ffmpeg: number; ffmpeg_rss_mb: number; render_queue: number; upload_queue: number }[] }
