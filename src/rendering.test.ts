import { describe, expect, it } from 'vitest';
import { changeRender, DEFAULT_RENDER, exportName, outputSize } from './rendering';

describe('render options', () => {
  it('keeps exact native pixels and fits landscape, portrait, square, and DCI footage', () => {
    expect(outputSize(101, 67, 'native')).toEqual([101, 67]);
    expect(outputSize(3840, 2160, '720p')).toEqual([1280, 720]);
    expect(outputSize(1080, 1920, '720p')).toEqual([720, 1280]);
    expect(outputSize(1920, 1080, '1080p')).toEqual([1920, 1080]);
    expect(outputSize(1920, 1080, '1440p')).toEqual([2560, 1440]);
    expect(outputSize(4096, 2160, '2k')).toEqual([2048, 1080]);
    expect(outputSize(1920, 1080, '4k')).toEqual([3840, 2160]);
    expect(outputSize(1920, 1920, '720p')).toEqual([720, 720]);
    expect(outputSize(96, 64, '720p')).toEqual([1080, 720]);
  });

  it('gives MP4 a visible background and preserves intentional colors', () => {
    expect(changeRender(DEFAULT_RENDER, { format: 'mp4' }).background).toBe('green');
    expect(changeRender({ ...DEFAULT_RENDER, background: 'blue' }, { format: 'mp4' }).background).toBe('blue');
    expect(DEFAULT_RENDER.background).toBe('transparent');
  });

  it('names videos and sequence folders with the selected style and size', () => {
    expect(exportName('clip', DEFAULT_RENDER)).toBe('clip-cutout.mov');
    expect(exportName('clip', changeRender(DEFAULT_RENDER, { format: 'mp4', resolution: '1080p' }))).toBe('clip-green-1080p.mp4');
    expect(exportName('clip', { ...DEFAULT_RENDER, format: 'png_sequence' })).toBe('clip-cutout-frames');
    expect(exportName('clip', { ...DEFAULT_RENDER, format: 'mask_sequence', resolution: '720p' })).toBe('clip-masks-720p');
  });
});
