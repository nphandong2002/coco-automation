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
export type AssetKind = "image" | "audio" | "video" | "font";
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
