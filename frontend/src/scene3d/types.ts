/** Mirrors backend/app/schemas/scene3d.py. */
export type Vec3 = [number, number, number];
export type Preset = "cozy_room" | "rainy_window" | "forest_cabin" | "cafe" | "library";
export type Pose = "stand" | "study";
export type CameraMotion = "static" | "drift" | "breathe";
export type TimeOfDay = "day" | "dusk" | "night";
export type ReactionTrigger = "click" | "rain_heavy" | "fire_out" | "break_time";
export type PickTarget = "window" | "fireplace" | "lamp" | "character";

export interface Environment3D { time_of_day: TimeOfDay; rain: number; wind: number; fog: number; fireplace: boolean; lamp: boolean }
export interface Character3D {
  asset_id: number | null; position: Vec3; rotation_y: number; scale: number; pose: Pose;
  idle_animation: string | null; reactions: Partial<Record<ReactionTrigger, string>>;
}
export interface Camera3D { position: Vec3; target: Vec3; fov: number; motion: CameraMotion; motion_amount: number }
export interface Scene3D { version: 1; preset: Preset; environment: Environment3D; character: Character3D; camera: Camera3D }

export const PRESETS: Record<Preset, string> = {
  cozy_room: "Phòng học ấm cúng", rainy_window: "Cửa sổ ngày mưa", forest_cabin: "Nhà gỗ trong rừng", cafe: "Quán cà phê",
  library: "Thư viện học bài (góc nhìn từ trên cao)",
};
export const TIMES: Record<TimeOfDay, string> = { day: "Ban ngày", dusk: "Hoàng hôn", night: "Ban đêm" };
export const TRIGGERS: Record<ReactionTrigger, string> = {
  click: "Khi bấm vào nhân vật (chỉ trong dashboard)", rain_heavy: "Khi mưa lớn (mưa ≥ 70%)",
  fire_out: "Khi lò sưởi tắt", break_time: "Khi bắt đầu giờ nghỉ Pomodoro",
};

export const defaultScene = (): Scene3D => ({
  version: 1, preset: "cozy_room",
  environment: { time_of_day: "night", rain: 0.5, wind: 0.2, fog: 0.1, fireplace: true, lamp: true },
  character: { asset_id: null, position: [0.9, 0, -0.2], rotation_y: -25, scale: 1, pose: "stand", idle_animation: null, reactions: {} },
  camera: { position: [0, 1.5, 3.6], target: [0, 0.9, 0], fov: 45, motion: "drift", motion_amount: 0.5 },
});

export const CAMERA_SHOTS: Record<string, { label: string; position: Vec3; target: Vec3; fov: number }> = {
  dollhouse: { label: "Từ trên cao nhìn xuống (nhà búp bê)", position: [0, 5.3, 6.4], target: [0, 0.5, -0.6], fov: 40 },
  wide: { label: "Toàn cảnh phòng", position: [0, 3.4, 7.4], target: [0, 1.2, -0.6], fov: 42 },
  closeup: { label: "Cận cảnh bàn học", position: [0, 2.4, 2.3], target: [0, 0.95, -1.0], fov: 40 },
  eye: { label: "Ngang tầm mắt", position: [0, 1.5, 3.6], target: [0, 0.9, 0], fov: 45 },
};
export const MOTIONS: Record<CameraMotion, string> = { static: "Đứng yên", drift: "Trôi nhẹ", breathe: "Tiến/lùi chậm" };

/** Changing the preset also picks a sensible pose + camera for it (the library is a seated study scene). */
export function withPreset(s: Scene3D, preset: Preset): Scene3D {
  if (preset === "library") {
    const shot = CAMERA_SHOTS.dollhouse;
    return { ...s, preset, character: { ...s.character, pose: "study", position: [0, 0, 0], rotation_y: 0 },
      camera: { ...s.camera, position: shot.position, target: shot.target, fov: shot.fov } };
  }
  if (s.preset === "library") {
    const d = defaultScene();
    return { ...s, preset, character: { ...s.character, pose: "stand", position: d.character.position, rotation_y: d.character.rotation_y }, camera: d.camera };
  }
  return { ...s, preset };
}
