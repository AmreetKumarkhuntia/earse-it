import { describe, expect, it } from 'vitest';
import { appendPoint, imageRect, makeBox, normalizePoint, timecode } from './geometry';

describe('selection coordinates', () => {
  it('accounts for letterboxing on portrait and landscape footage', () => {
    const landscape = imageRect({ width: 800, height: 600 }, 16/9);
    expect(landscape).toEqual({ x: 0, y: 75, width: 800, height: 450 });
    expect(normalizePoint(400, 300, landscape)).toEqual([.5, .5]);
    expect(normalizePoint(400, 40, landscape)).toBeNull();
    const portrait = imageRect({ width: 800, height: 600 }, 9/16);
    expect(normalizePoint(400, 300, portrait)).toEqual([.5, .5]);
    expect(normalizePoint(20, 300, portrait)).toBeNull();
  });
  it('supports boxes drawn in any direction without zero-sized prompts', () => {
    expect(makeBox([.8, .9], [.2, .1])).toEqual([.2, .1, .8, .9]);
    expect(makeBox([.1, .1], [.1, .1])).toBeNull();
  });
  it('samples strokes without dropping an opposing label', () => {
    expect(appendPoint([[.5,.5,1]], [.501,.501,1])).toHaveLength(1);
    expect(appendPoint([[.5,.5,1]], [.501,.501,0])).toHaveLength(2);
  });
  it('formats elapsed frame time without rounding up a frame', () => {
    expect(timecode(31, 30)).toBe('00:00:01:01');
    expect(timecode(1800, 30)).toBe('00:01:00:00');
  });
});
