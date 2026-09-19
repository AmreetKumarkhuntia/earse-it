import { convertFileSrc, invoke, isTauri } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { WorkerEvent } from './types';

type Response = { v: number; id?: string; result?: unknown; error?: { code: string; message: string }; event?: string };
export class WorkerError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

const pending = new Map<string, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
const subscribers = new Set<(event: WorkerEvent) => void>();
let listening: Promise<void> | undefined;
let queue: Promise<unknown> = Promise.resolve();
const cancelled = new Set<string>();

export const desktop = isTauri();
export const asset = (path: string) => desktop ? convertFileSrc(path) : path;

function initialize() {
  if (!desktop) return Promise.reject(new WorkerError('DESKTOP_REQUIRED', 'Open the desktop app to process local videos. This browser window previews the interface.'));
  listening ??= listen<Response>('worker-message', ({ payload }) => {
    if (payload.event) {
      const event = payload as unknown as WorkerEvent;
      subscribers.forEach(callback => callback(event));
      if (event.event === 'worker-error') {
        pending.forEach(item => item.reject(new WorkerError('WORKER_EXITED', event.message)));
        pending.clear();
      }
    } else if (payload.id) {
      const item = pending.get(payload.id);
      if (!item) return;
      pending.delete(payload.id);
      if (payload.error) item.reject(new WorkerError(payload.error.code, payload.error.message));
      else item.resolve(payload.result);
    }
  }).then(() => undefined).catch(error => { listening = undefined; throw error; });
  return listening;
}

async function send<T>(id: string, action: string, params: Record<string, unknown>): Promise<T> {
  await initialize();
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: value => resolve(value as T), reject });
    invoke('worker_request', { request: { v: 1, id, action, params } }).catch(error => {
      pending.delete(id);
      reject(error instanceof Error ? error : new Error(String(error)));
    });
  });
}

export function request<T>(action: string, params: Record<string, unknown> = {}) {
  const id = crypto.randomUUID();
  const promise = queue.catch(() => undefined).then(() => {
    if (cancelled.delete(id)) throw new WorkerError('CANCELLED', 'Operation cancelled.');
    return send<T>(id, action, params);
  });
  queue = promise.catch(() => undefined);
  return { id, promise };
}

export async function cancel(id: string) {
  if (!pending.has(id)) { cancelled.add(id); return; }
  await send(crypto.randomUUID(), 'cancel', { job_id: id });
}

export function subscribe(callback: (event: WorkerEvent) => void) {
  subscribers.add(callback);
  return () => { subscribers.delete(callback); };
}
