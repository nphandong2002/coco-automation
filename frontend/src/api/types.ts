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
