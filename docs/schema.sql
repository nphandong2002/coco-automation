\restrict olplMDgx4hqG8GjkTRQZ6kwJtLsC9a4ZFZxGNCHYsYxy3SgI37hqOsCn8qkN6u8
COMMENT ON SCHEMA public IS '';
CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);
CREATE TABLE public.analytics_daily (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    day date NOT NULL,
    views bigint NOT NULL,
    watch_time_minutes double precision NOT NULL,
    average_view_duration_sec double precision,
    average_view_percentage double precision,
    subscribers_gained integer NOT NULL,
    subscribers_lost integer NOT NULL,
    likes integer NOT NULL,
    comments integer NOT NULL,
    data_source character varying(32) NOT NULL,
    synced_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_analytics_daily_data_source CHECK (((data_source)::text = ANY (ARRAY[('youtube_api'::character varying)::text, ('estimated'::character varying)::text])))
);
CREATE SEQUENCE public.analytics_daily_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.analytics_daily_id_seq OWNED BY public.analytics_daily.id;
CREATE TABLE public.analytics_video (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    video_id integer NOT NULL,
    day date NOT NULL,
    views bigint NOT NULL,
    watch_time_minutes double precision NOT NULL,
    average_view_duration_sec double precision,
    average_view_percentage double precision,
    subscribers_gained integer NOT NULL,
    likes integer NOT NULL,
    comments integer NOT NULL,
    data_source character varying(32) NOT NULL,
    synced_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_analytics_video_data_source CHECK (((data_source)::text = ANY (ARRAY[('youtube_api'::character varying)::text, ('estimated'::character varying)::text])))
);
CREATE SEQUENCE public.analytics_video_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.analytics_video_id_seq OWNED BY public.analytics_video.id;
CREATE TABLE public.assets (
    id integer NOT NULL,
    channel_id integer,
    kind character varying(32) NOT NULL,
    name character varying(200) NOT NULL,
    file_path character varying(512) NOT NULL,
    sha256 character varying(64) NOT NULL,
    size_bytes bigint NOT NULL,
    mime_type character varying(100) NOT NULL,
    duration_sec double precision,
    width integer,
    height integer,
    license_type character varying(32) NOT NULL,
    license_source character varying(500) NOT NULL,
    attribution character varying(500) NOT NULL,
    tags json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_assets_asset_kind CHECK (((kind)::text = ANY (ARRAY[('image'::character varying)::text, ('video'::character varying)::text, ('audio'::character varying)::text, ('font'::character varying)::text]))),
    CONSTRAINT ck_assets_license_type CHECK (((license_type)::text = ANY (ARRAY[('owned'::character varying)::text, ('cc0'::character varying)::text, ('cc_by'::character varying)::text, ('royalty_free'::character varying)::text, ('licensed'::character varying)::text])))
);
CREATE SEQUENCE public.assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.assets_id_seq OWNED BY public.assets.id;
CREATE TABLE public.channel_characters (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    character_id integer NOT NULL,
    role character varying(32) NOT NULL,
    is_owner boolean NOT NULL,
    granted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    note character varying(300) NOT NULL,
    CONSTRAINT ck_channel_characters_character_role CHECK (((role)::text = ANY (ARRAY[('primary'::character varying)::text, ('secondary'::character varying)::text])))
);
CREATE SEQUENCE public.channel_characters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.channel_characters_id_seq OWNED BY public.channel_characters.id;
CREATE TABLE public.channels (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(150) NOT NULL,
    description text NOT NULL,
    language character varying(16) NOT NULL,
    target_country character varying(8) NOT NULL,
    topics json NOT NULL,
    visual_style json NOT NULL,
    audio_style json NOT NULL,
    publish_schedule json NOT NULL,
    avatar_path character varying(512),
    banner_path character varying(512),
    enabled boolean NOT NULL,
    last_error text,
    last_error_at timestamp with time zone,
    cloned_from_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.channels_id_seq OWNED BY public.channels.id;
CREATE TABLE public.character_versions (
    id integer NOT NULL,
    character_id integer NOT NULL,
    version_no integer NOT NULL,
    appearance text NOT NULL,
    art_style character varying(200) NOT NULL,
    primary_colors json NOT NULL,
    outfit text NOT NULL,
    personality text NOT NULL,
    usual_settings json NOT NULL,
    allowed_animations json NOT NULL,
    expressions json NOT NULL,
    avatar_image character varying(512),
    full_body_image character varying(512),
    reference_images json NOT NULL,
    change_note character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE SEQUENCE public.character_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.character_versions_id_seq OWNED BY public.character_versions.id;
CREATE TABLE public.characters (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    name character varying(120) NOT NULL,
    species character varying(80) NOT NULL,
    current_version_id integer,
    archived boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE public.characters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.characters_id_seq OWNED BY public.characters.id;
CREATE TABLE public.content_ideas (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    title character varying(200) NOT NULL,
    content_type character varying(32) NOT NULL,
    theme character varying(200) NOT NULL,
    description text NOT NULL,
    attributes json NOT NULL,
    fingerprint character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_content_ideas_content_type CHECK (((content_type)::text = ANY (ARRAY[('study_with_me'::character varying)::text, ('pomodoro'::character varying)::text, ('cozy_ambience'::character varying)::text, ('rain_sounds'::character varying)::text, ('fireplace_sounds'::character varying)::text, ('sleep_ambience'::character varying)::text, ('reading_room'::character varying)::text, ('cafe_ambience'::character varying)::text, ('nature_ambience'::character varying)::text]))),
    CONSTRAINT ck_content_ideas_idea_status CHECK (((status)::text = ANY (ARRAY[('new'::character varying)::text, ('accepted'::character varying)::text, ('rejected'::character varying)::text, ('used'::character varying)::text])))
);
CREATE SEQUENCE public.content_ideas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.content_ideas_id_seq OWNED BY public.content_ideas.id;
CREATE TABLE public.content_projects (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    idea_id integer,
    template_id integer,
    character_id integer,
    character_version_id integer,
    title character varying(200) NOT NULL,
    content_type character varying(32) NOT NULL,
    theme character varying(200) NOT NULL,
    script text NOT NULL,
    setting character varying(200) NOT NULL,
    background_asset_id integer,
    animation json NOT NULL,
    audio_layers json NOT NULL,
    duration_minutes integer NOT NULL,
    pomodoro json,
    youtube_title character varying(100) NOT NULL,
    youtube_description text NOT NULL,
    youtube_tags json NOT NULL,
    thumbnail_path character varying(512),
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_content_projects_content_type CHECK (((content_type)::text = ANY (ARRAY[('study_with_me'::character varying)::text, ('pomodoro'::character varying)::text, ('cozy_ambience'::character varying)::text, ('rain_sounds'::character varying)::text, ('fireplace_sounds'::character varying)::text, ('sleep_ambience'::character varying)::text, ('reading_room'::character varying)::text, ('cafe_ambience'::character varying)::text, ('nature_ambience'::character varying)::text]))),
    CONSTRAINT ck_content_projects_production_status CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('ready'::character varying)::text, ('queued'::character varying)::text, ('rendering'::character varying)::text, ('rendered'::character varying)::text, ('failed'::character varying)::text, ('published'::character varying)::text])))
);
CREATE SEQUENCE public.content_projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.content_projects_id_seq OWNED BY public.content_projects.id;
CREATE TABLE public.publishing_jobs (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    video_id integer NOT NULL,
    status character varying(32) NOT NULL,
    privacy_status character varying(32) NOT NULL,
    publish_at timestamp with time zone,
    title character varying(100) NOT NULL,
    description text NOT NULL,
    tags json NOT NULL,
    playlist_id character varying(64),
    category_id character varying(8) NOT NULL,
    upload_session_uri text,
    bytes_uploaded bigint NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    next_attempt_at timestamp with time zone,
    youtube_video_id character varying(32),
    uploaded_at timestamp with time zone,
    last_error text,
    history json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_publishing_jobs_job_status CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('running'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text, ('cancelled'::character varying)::text]))),
    CONSTRAINT ck_publishing_jobs_privacy_status CHECK (((privacy_status)::text = ANY (ARRAY[('private'::character varying)::text, ('unlisted'::character varying)::text, ('public'::character varying)::text])))
);
CREATE SEQUENCE public.publishing_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.publishing_jobs_id_seq OWNED BY public.publishing_jobs.id;
CREATE TABLE public.scheduler_jobs (
    id integer NOT NULL,
    channel_id integer,
    job_type character varying(64) NOT NULL,
    payload json NOT NULL,
    dedupe_key character varying(200),
    status character varying(32) NOT NULL,
    run_at timestamp with time zone NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    timeout_sec integer NOT NULL,
    locked_by character varying(100),
    locked_at timestamp with time zone,
    finished_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_scheduler_jobs_job_status CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('running'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text, ('cancelled'::character varying)::text])))
);
CREATE SEQUENCE public.scheduler_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.scheduler_jobs_id_seq OWNED BY public.scheduler_jobs.id;
CREATE TABLE public.system_logs (
    id integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    level character varying(32) NOT NULL,
    category character varying(50) NOT NULL,
    channel_id integer,
    message character varying(500) NOT NULL,
    details json NOT NULL,
    CONSTRAINT ck_system_logs_log_level CHECK (((level)::text = ANY (ARRAY[('debug'::character varying)::text, ('info'::character varying)::text, ('warning'::character varying)::text, ('error'::character varying)::text])))
);
CREATE SEQUENCE public.system_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.system_logs_id_seq OWNED BY public.system_logs.id;
CREATE TABLE public.video_jobs (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    content_project_id integer NOT NULL,
    status character varying(32) NOT NULL,
    priority integer NOT NULL,
    progress double precision NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    worker_id character varying(100),
    heartbeat_at timestamp with time zone,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    render_config json NOT NULL,
    output_path character varying(512),
    log_path character varying(512),
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_video_jobs_job_status CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('running'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text, ('cancelled'::character varying)::text])))
);
CREATE SEQUENCE public.video_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.video_jobs_id_seq OWNED BY public.video_jobs.id;
CREATE TABLE public.video_templates (
    id integer NOT NULL,
    channel_id integer,
    name character varying(150) NOT NULL,
    content_type character varying(32) NOT NULL,
    config json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_video_templates_content_type CHECK (((content_type)::text = ANY (ARRAY[('study_with_me'::character varying)::text, ('pomodoro'::character varying)::text, ('cozy_ambience'::character varying)::text, ('rain_sounds'::character varying)::text, ('fireplace_sounds'::character varying)::text, ('sleep_ambience'::character varying)::text, ('reading_room'::character varying)::text, ('cafe_ambience'::character varying)::text, ('nature_ambience'::character varying)::text])))
);
CREATE SEQUENCE public.video_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.video_templates_id_seq OWNED BY public.video_templates.id;
CREATE TABLE public.videos (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    content_project_id integer,
    video_job_id integer,
    title character varying(200) NOT NULL,
    file_path character varying(512) NOT NULL,
    duration_sec double precision NOT NULL,
    width integer NOT NULL,
    height integer NOT NULL,
    fps double precision NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 character varying(64),
    thumbnail_path character varying(512),
    qc_report json NOT NULL,
    youtube_video_id character varying(32),
    privacy_status character varying(32),
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_videos_privacy_status CHECK (((privacy_status)::text = ANY (ARRAY[('private'::character varying)::text, ('unlisted'::character varying)::text, ('public'::character varying)::text])))
);
CREATE SEQUENCE public.videos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.videos_id_seq OWNED BY public.videos.id;
CREATE TABLE public.youtube_credentials (
    id integer NOT NULL,
    channel_id integer NOT NULL,
    youtube_channel_id character varying(64),
    youtube_channel_title character varying(200),
    google_account_email character varying(200),
    scopes json NOT NULL,
    token_encrypted bytea NOT NULL,
    token_expiry timestamp with time zone,
    status character varying(32) NOT NULL,
    last_refresh_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_youtube_credentials_credential_status CHECK (((status)::text = ANY (ARRAY[('valid'::character varying)::text, ('expired'::character varying)::text, ('revoked'::character varying)::text])))
);
CREATE SEQUENCE public.youtube_credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.youtube_credentials_id_seq OWNED BY public.youtube_credentials.id;
ALTER TABLE ONLY public.analytics_daily ALTER COLUMN id SET DEFAULT nextval('public.analytics_daily_id_seq'::regclass);
ALTER TABLE ONLY public.analytics_video ALTER COLUMN id SET DEFAULT nextval('public.analytics_video_id_seq'::regclass);
ALTER TABLE ONLY public.assets ALTER COLUMN id SET DEFAULT nextval('public.assets_id_seq'::regclass);
ALTER TABLE ONLY public.channel_characters ALTER COLUMN id SET DEFAULT nextval('public.channel_characters_id_seq'::regclass);
ALTER TABLE ONLY public.channels ALTER COLUMN id SET DEFAULT nextval('public.channels_id_seq'::regclass);
ALTER TABLE ONLY public.character_versions ALTER COLUMN id SET DEFAULT nextval('public.character_versions_id_seq'::regclass);
ALTER TABLE ONLY public.characters ALTER COLUMN id SET DEFAULT nextval('public.characters_id_seq'::regclass);
ALTER TABLE ONLY public.content_ideas ALTER COLUMN id SET DEFAULT nextval('public.content_ideas_id_seq'::regclass);
ALTER TABLE ONLY public.content_projects ALTER COLUMN id SET DEFAULT nextval('public.content_projects_id_seq'::regclass);
ALTER TABLE ONLY public.publishing_jobs ALTER COLUMN id SET DEFAULT nextval('public.publishing_jobs_id_seq'::regclass);
ALTER TABLE ONLY public.scheduler_jobs ALTER COLUMN id SET DEFAULT nextval('public.scheduler_jobs_id_seq'::regclass);
ALTER TABLE ONLY public.system_logs ALTER COLUMN id SET DEFAULT nextval('public.system_logs_id_seq'::regclass);
ALTER TABLE ONLY public.video_jobs ALTER COLUMN id SET DEFAULT nextval('public.video_jobs_id_seq'::regclass);
ALTER TABLE ONLY public.video_templates ALTER COLUMN id SET DEFAULT nextval('public.video_templates_id_seq'::regclass);
ALTER TABLE ONLY public.videos ALTER COLUMN id SET DEFAULT nextval('public.videos_id_seq'::regclass);
ALTER TABLE ONLY public.youtube_credentials ALTER COLUMN id SET DEFAULT nextval('public.youtube_credentials_id_seq'::regclass);
ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
ALTER TABLE ONLY public.analytics_daily
    ADD CONSTRAINT pk_analytics_daily PRIMARY KEY (id);
ALTER TABLE ONLY public.analytics_video
    ADD CONSTRAINT pk_analytics_video PRIMARY KEY (id);
ALTER TABLE ONLY public.assets
    ADD CONSTRAINT pk_assets PRIMARY KEY (id);
ALTER TABLE ONLY public.channel_characters
    ADD CONSTRAINT pk_channel_characters PRIMARY KEY (id);
ALTER TABLE ONLY public.channels
    ADD CONSTRAINT pk_channels PRIMARY KEY (id);
ALTER TABLE ONLY public.character_versions
    ADD CONSTRAINT pk_character_versions PRIMARY KEY (id);
ALTER TABLE ONLY public.characters
    ADD CONSTRAINT pk_characters PRIMARY KEY (id);
ALTER TABLE ONLY public.content_ideas
    ADD CONSTRAINT pk_content_ideas PRIMARY KEY (id);
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT pk_content_projects PRIMARY KEY (id);
ALTER TABLE ONLY public.publishing_jobs
    ADD CONSTRAINT pk_publishing_jobs PRIMARY KEY (id);
ALTER TABLE ONLY public.scheduler_jobs
    ADD CONSTRAINT pk_scheduler_jobs PRIMARY KEY (id);
ALTER TABLE ONLY public.system_logs
    ADD CONSTRAINT pk_system_logs PRIMARY KEY (id);
ALTER TABLE ONLY public.video_jobs
    ADD CONSTRAINT pk_video_jobs PRIMARY KEY (id);
ALTER TABLE ONLY public.video_templates
    ADD CONSTRAINT pk_video_templates PRIMARY KEY (id);
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT pk_videos PRIMARY KEY (id);
ALTER TABLE ONLY public.youtube_credentials
    ADD CONSTRAINT pk_youtube_credentials PRIMARY KEY (id);
ALTER TABLE ONLY public.analytics_daily
    ADD CONSTRAINT uq_analytics_daily_channel_id_day UNIQUE (channel_id, day);
ALTER TABLE ONLY public.analytics_video
    ADD CONSTRAINT uq_analytics_video_video_id_day UNIQUE (video_id, day);
ALTER TABLE ONLY public.assets
    ADD CONSTRAINT uq_assets_channel_id_sha256 UNIQUE (channel_id, sha256);
ALTER TABLE ONLY public.channel_characters
    ADD CONSTRAINT uq_channel_characters_channel_id_character_id UNIQUE (channel_id, character_id);
ALTER TABLE ONLY public.channels
    ADD CONSTRAINT uq_channels_code UNIQUE (code);
ALTER TABLE ONLY public.character_versions
    ADD CONSTRAINT uq_character_versions_character_id_id UNIQUE (character_id, id);
ALTER TABLE ONLY public.character_versions
    ADD CONSTRAINT uq_character_versions_character_id_version_no UNIQUE (character_id, version_no);
ALTER TABLE ONLY public.characters
    ADD CONSTRAINT uq_characters_channel_id_name UNIQUE (channel_id, name);
ALTER TABLE ONLY public.content_ideas
    ADD CONSTRAINT uq_content_ideas_channel_id_fingerprint UNIQUE (channel_id, fingerprint);
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT uq_content_projects_channel_id_id UNIQUE (channel_id, id);
ALTER TABLE ONLY public.scheduler_jobs
    ADD CONSTRAINT uq_scheduler_jobs_dedupe_key UNIQUE (dedupe_key);
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT uq_videos_channel_id_id UNIQUE (channel_id, id);
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT uq_videos_youtube_video_id UNIQUE (youtube_video_id);
ALTER TABLE ONLY public.youtube_credentials
    ADD CONSTRAINT uq_youtube_credentials_channel_id UNIQUE (channel_id);
ALTER TABLE ONLY public.youtube_credentials
    ADD CONSTRAINT uq_youtube_credentials_youtube_channel_id UNIQUE (youtube_channel_id);
CREATE INDEX ix_analytics_daily_channel_id ON public.analytics_daily USING btree (channel_id);
CREATE INDEX ix_analytics_video_channel_id ON public.analytics_video USING btree (channel_id);
CREATE INDEX ix_assets_channel_id ON public.assets USING btree (channel_id);
CREATE INDEX ix_channel_characters_channel_id ON public.channel_characters USING btree (channel_id);
CREATE INDEX ix_channel_characters_character_id ON public.channel_characters USING btree (character_id);
CREATE INDEX ix_character_versions_character_id ON public.character_versions USING btree (character_id);
CREATE INDEX ix_characters_channel_id ON public.characters USING btree (channel_id);
CREATE INDEX ix_content_ideas_channel_id ON public.content_ideas USING btree (channel_id);
CREATE INDEX ix_content_projects_channel_id ON public.content_projects USING btree (channel_id);
CREATE INDEX ix_publishing_jobs_channel_id ON public.publishing_jobs USING btree (channel_id);
CREATE INDEX ix_publishing_jobs_status ON public.publishing_jobs USING btree (status);
CREATE INDEX ix_scheduler_jobs_channel_id ON public.scheduler_jobs USING btree (channel_id);
CREATE INDEX ix_scheduler_jobs_run_at ON public.scheduler_jobs USING btree (run_at);
CREATE INDEX ix_scheduler_jobs_status ON public.scheduler_jobs USING btree (status);
CREATE INDEX ix_system_logs_category ON public.system_logs USING btree (category);
CREATE INDEX ix_system_logs_channel_id ON public.system_logs USING btree (channel_id);
CREATE INDEX ix_system_logs_created_at ON public.system_logs USING btree (created_at);
CREATE INDEX ix_video_jobs_channel_id ON public.video_jobs USING btree (channel_id);
CREATE INDEX ix_video_jobs_status ON public.video_jobs USING btree (status);
CREATE INDEX ix_video_templates_channel_id ON public.video_templates USING btree (channel_id);
CREATE INDEX ix_videos_channel_id ON public.videos USING btree (channel_id);
CREATE UNIQUE INDEX uq_channel_characters_one_primary ON public.channel_characters USING btree (channel_id) WHERE ((role)::text = 'primary'::text);
ALTER TABLE ONLY public.analytics_daily
    ADD CONSTRAINT fk_analytics_daily_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.analytics_video
    ADD CONSTRAINT fk_analytics_video_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.analytics_video
    ADD CONSTRAINT fk_analytics_video_video FOREIGN KEY (channel_id, video_id) REFERENCES public.videos(channel_id, id) ON DELETE CASCADE;
ALTER TABLE ONLY public.assets
    ADD CONSTRAINT fk_assets_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.channel_characters
    ADD CONSTRAINT fk_channel_characters_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.channel_characters
    ADD CONSTRAINT fk_channel_characters_character_id_characters FOREIGN KEY (character_id) REFERENCES public.characters(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.channels
    ADD CONSTRAINT fk_channels_cloned_from_id_channels FOREIGN KEY (cloned_from_id) REFERENCES public.channels(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.character_versions
    ADD CONSTRAINT fk_character_versions_character_id_characters FOREIGN KEY (character_id) REFERENCES public.characters(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.characters
    ADD CONSTRAINT fk_characters_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.characters
    ADD CONSTRAINT fk_characters_current_version_id_character_versions FOREIGN KEY (current_version_id) REFERENCES public.character_versions(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.content_ideas
    ADD CONSTRAINT fk_content_ideas_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_background_asset_id_assets FOREIGN KEY (background_asset_id) REFERENCES public.assets(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_channel_character FOREIGN KEY (channel_id, character_id) REFERENCES public.channel_characters(channel_id, character_id);
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_character_version FOREIGN KEY (character_id, character_version_id) REFERENCES public.character_versions(character_id, id);
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_idea_id_content_ideas FOREIGN KEY (idea_id) REFERENCES public.content_ideas(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.content_projects
    ADD CONSTRAINT fk_content_projects_template_id_video_templates FOREIGN KEY (template_id) REFERENCES public.video_templates(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.publishing_jobs
    ADD CONSTRAINT fk_publishing_jobs_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.publishing_jobs
    ADD CONSTRAINT fk_publishing_jobs_video FOREIGN KEY (channel_id, video_id) REFERENCES public.videos(channel_id, id) ON DELETE CASCADE;
ALTER TABLE ONLY public.scheduler_jobs
    ADD CONSTRAINT fk_scheduler_jobs_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.system_logs
    ADD CONSTRAINT fk_system_logs_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.video_jobs
    ADD CONSTRAINT fk_video_jobs_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.video_jobs
    ADD CONSTRAINT fk_video_jobs_project FOREIGN KEY (channel_id, content_project_id) REFERENCES public.content_projects(channel_id, id) ON DELETE CASCADE;
ALTER TABLE ONLY public.video_templates
    ADD CONSTRAINT fk_video_templates_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT fk_videos_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT fk_videos_project FOREIGN KEY (channel_id, content_project_id) REFERENCES public.content_projects(channel_id, id) ON DELETE SET NULL;
ALTER TABLE ONLY public.videos
    ADD CONSTRAINT fk_videos_video_job_id_video_jobs FOREIGN KEY (video_job_id) REFERENCES public.video_jobs(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.youtube_credentials
    ADD CONSTRAINT fk_youtube_credentials_channel_id_channels FOREIGN KEY (channel_id) REFERENCES public.channels(id) ON DELETE CASCADE;
\unrestrict olplMDgx4hqG8GjkTRQZ6kwJtLsC9a4ZFZxGNCHYsYxy3SgI37hqOsCn8qkN6u8
