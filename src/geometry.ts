import type { Box, Point, Project } from './types';

export const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));

/** Convert pointer coordinates through letterboxing, without changing the model's normalized space. */
export function imageRect(container: { width: number; height: number }, aspect: number) {
  const width = Math.min(container.width, container.height * aspect);
  const height = width / aspect;
  return { x: (container.width - width) / 2, y: (container.height - height) / 2, width, height };
}

export function normalizePoint(x: number, y: number, rect: ReturnType<typeof imageRect>): [number, number] | null {
  if (!rect.width || !rect.height || x < rect.x || y < rect.y || x > rect.x + rect.width || y > rect.y + rect.height) return null;
  return [clamp((x - rect.x) / rect.width), clamp((y - rect.y) / rect.height)];
}

export function makeBox(start: [number, number], end: [number, number]): Box | null {
  const box: Box = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])];
  return box[2] - box[0] < .003 || box[3] - box[1] < .003 ? null : box;
}

export function appendPoint(points: Point[], point: Point): Point[] {
  if (points.length >= 128) return points;
  const last = points.at(-1);
  if (last && last[2] === point[2] && Math.hypot(last[0] - point[0], last[1] - point[1]) < .012) return points;
  return [...points, point];
}

export function timecode(frame: number, fps: number): string {
  const total = Math.max(0, frame / fps);
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, Math.floor(total) % 60, Math.floor((total % 1) * fps + .0001)]
    .map(value => String(value).padStart(2, '0')).join(':');
}

export function coveredFrames(project: Project): number {
  return project.tracked_ranges.reduce((sum, [start, end]) => sum + Math.max(0, Math.min(end, project.out_frame) - Math.max(start, project.in_frame) + 1), 0);
}
