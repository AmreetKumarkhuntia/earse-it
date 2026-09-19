import type { RenderSettings } from './types';

export const DEFAULT_RENDER: RenderSettings = {
  format: 'prores', background: 'transparent', color: '#00ff00',
  resolution: 'native', quality: 'high', audio: true,
};

export const RESOLUTIONS = [
  { id: 'native', label: 'Native · original pixels', width: 0, height: 0 },
  { id: '720p', label: '720p · HD', width: 1280, height: 720 },
  { id: '1080p', label: '1080p · Full HD', width: 1920, height: 1080 },
  { id: '1440p', label: '1440p · QHD', width: 2560, height: 1440 },
  { id: '2k', label: '2K · DCI', width: 2048, height: 1080 },
  { id: '4k', label: '4K · Ultra HD', width: 3840, height: 2160 },
] as const;

export function outputSize(width: number, height: number, resolution: RenderSettings['resolution']) {
  if (resolution === 'native') return [width, height] as const;
  const preset = RESOLUTIONS.find(item => item.id === resolution)!;
  const [boundWidth, boundHeight] = height > width ? [preset.height, preset.width] : [preset.width, preset.height];
  const scale = Math.min(boundWidth / width, boundHeight / height);
  return [Math.max(2, Math.floor(width * scale / 2 + 1e-9) * 2), Math.max(2, Math.floor(height * scale / 2 + 1e-9) * 2)] as const;
}

export function changeRender(settings: RenderSettings, changes: Partial<RenderSettings>): RenderSettings {
  const next = { ...settings, ...changes };
  if (next.format === 'mp4' && next.background === 'transparent') next.background = 'green';
  return next;
}

export function exportName(name: string, settings: RenderSettings) {
  const suffix = settings.resolution === 'native' ? '' : `-${settings.resolution}`;
  if (settings.format === 'mask_sequence') return `${name}-masks${suffix}`;
  const background = settings.background === 'transparent' ? 'cutout' : settings.background;
  const extension = settings.format === 'mp4' ? '.mp4' : settings.format === 'prores' ? '.mov' : '';
  return `${name}-${background}${suffix}${settings.format === 'png_sequence' ? '-frames' : extension}`;
}
