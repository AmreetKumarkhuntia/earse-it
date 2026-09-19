import { describe, expect, it } from 'vitest';
import { processingStatus } from './processing';
import type { Hello } from './types';

const cpu: Hello['capabilities'] = {
  inference_ready: true, cpu_available: true, cuda_available: false,
  cuda_device: null, media_ready: true, gpu_status: 'cpu_only', cuda_runtime: null,
};

describe('processor guidance', () => {
  it('explains that Automatic cannot use CUDA with the CPU runtime', () => {
    expect(processingStatus(cpu).detail).toContain('separate NVIDIA runtime pack');
  });
  it('distinguishes a missing pack from a CUDA driver or hardware problem', () => {
    const status = processingStatus({ ...cpu, gpu_status: 'cuda_unavailable', cuda_runtime: '12.8' });
    expect(status.detail).toContain('CUDA 12.8 runtime is installed');
    expect(status.detail).toContain('driver');
  });
  it('honors an explicit CPU preference even with a GPU available', () => {
    const gpu = { ...cpu, cuda_available: true, cuda_device: 'NVIDIA test GPU' };
    expect(processingStatus(gpu, 'cpu').label).toBe('CPU selected');
    expect(processingStatus(gpu, 'auto').label).toContain('NVIDIA test GPU');
    expect(processingStatus(gpu, 'cuda').label).toContain('NVIDIA test GPU');
  });
  it('does not promise CPU fallback for an explicitly requested but unavailable GPU', () => {
    expect(processingStatus(cpu, 'cuda').label).toBe('Requested NVIDIA GPU unavailable');
  });
  it('does not report a broken or disconnected runtime as ready', () => {
    expect(processingStatus({ ...cpu, inference_ready: false }).label).toContain('unavailable');
    expect(processingStatus(undefined).label).toContain('Waiting');
  });
});
