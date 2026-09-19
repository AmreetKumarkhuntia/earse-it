import type { Hello, Project } from './types';

export function processingStatus(capabilities: Hello['capabilities'] | undefined, preference: Project['device'] = 'auto') {
  if (!capabilities) return { label: 'Waiting for processing runtime', detail: 'Open the desktop app to check GPU availability.' };
  if (!capabilities.inference_ready) return {
    label: 'Processing runtime unavailable',
    detail: 'The runtime could not load. Reinstall the app or its matching NVIDIA pack, then restart erase-it.',
  };
  if (capabilities.cuda_available) return preference === 'cpu' ? {
    label: 'CPU selected', detail: `${capabilities.cuda_device ?? 'NVIDIA GPU'} is available. Choose Automatic or NVIDIA GPU to use it.`,
  } : { label: `GPU · ${capabilities.cuda_device ?? 'NVIDIA'}`, detail: 'Selection and tracking will use your NVIDIA GPU.' };
  const detail = capabilities.gpu_status === 'cpu_only'
    ? 'The CPU runtime is installed. NVIDIA GPUs need the separate NVIDIA runtime pack.'
    : capabilities.gpu_status === 'cuda_unavailable'
      ? `The CUDA ${capabilities.cuda_runtime ?? ''} runtime is installed, but no usable NVIDIA GPU was detected. Check your GPU and NVIDIA driver.`
      : 'No usable NVIDIA GPU was detected. Check the runtime pack and NVIDIA driver.';
  return { label: preference === 'cuda' ? 'Requested NVIDIA GPU unavailable' : 'CPU · GPU unavailable', detail };
}
