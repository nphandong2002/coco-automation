"""FFmpeg rendering engine (no database access).

Modules:
  ffmpeg     – locate binaries, run a command with progress / cancel / timeout / low priority
  probe      – read media info (ffprobe, or ffmpeg fallback)
  fonts      – find a TTF/OTF font for text overlays
  timeline   – Pomodoro / countdown timeline + YouTube chapters
  scene      – Pillow: normalised backgrounds, procedural backgrounds, particle textures
  audio      – audio filtergraph (asset loops + procedural generators + chimes)
  video      – video filtergraphs (seamless base loop + timer overlay)
  thumbnail  – Pillow thumbnail 1280x720
  metadata   – YouTube title / description / tags
  qc         – post-render quality checks
  pipeline   – executes a RenderPlan step by step

A render is driven by a JSON-serialisable *plan* (see pipeline.RenderPlan) snapshotted
in `video_jobs.render_config`, so a retry renders exactly the same video.
"""
