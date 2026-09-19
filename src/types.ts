export type Point = [number, number, 0 | 1];
export type Box = [number, number, number, number];
export type Prompt = { points: Point[]; box: Box | null };
export type Prompts = Record<string, Prompt>;
export type Edge = { feather: number; grow: number; invert: boolean };
export type PreviewMode = 'overlay' | 'cutout' | 'mask' | 'original';
export type Tool = 'keep' | 'remove' | 'box';
export type Project = {
  schema_version: 1; id: string; name: string; source: string;
  media: { width: number; height: number; fps_num: number; fps_den: number; duration: number; frame_count: number; has_audio: boolean; normalized_timing: boolean };
  in_frame: number; out_frame: number; model: string; device: 'auto' | 'cpu' | 'cuda';
  edge: Edge; prompts: Prompts; revision: number; project_file: string | null;
  tracked_ranges: [number, number][]; directory: string; proxy: string;
};
export type Model = { id: string; name: string; description: string; size: number; installed: boolean; license: string };
export type Hello = {
  protocol: number; version: string; models: Model[]; last_project: string | null;
  capabilities: { inference_ready: boolean; cuda_available: boolean; cuda_device: string | null; cpu_available: boolean; media_ready: boolean };
};
export type Progress = { event: 'progress'; job_id: string; stage: string; current: number; total: number; elapsed: number; frame?: number; device?: string };
export type FrameResult = { path: string; has_mask: boolean; frame: number };
export type WorkerEvent = Progress | { event: 'worker-error'; message: string };
