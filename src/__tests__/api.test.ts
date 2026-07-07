import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

const BASE = 'http://127.0.0.1:8765/api';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const api = {
  monitor: {
    system: () => fetchJSON<{ hostname: string; os: string }>(`${BASE}/monitor/system`),
    cpu: () => fetchJSON<{ percent: number; cores: { physical: number; logical: number } }>(`${BASE}/monitor/cpu`),
    memory: () => fetchJSON<{ percent: number; total: number }>(`${BASE}/monitor/memory`),
    disk: () => fetchJSON<{ partitions: { mount: string; percent: number }[] }>(`${BASE}/monitor/disk`),
    processes: () => fetchJSON<{ pid: number; name: string }[]>(`${BASE}/monitor/processes`),
  },
  executor: {
    command: (cmd: string, timeout = 30) =>
      postJSON<{ stdout: string; returncode: number }>(`${BASE}/executor/command`, { command: cmd, timeout }),
  },
  ai: {
    chat: (msg: string) =>
      postJSON<{ response: string; model: string }>(`${BASE}/ai/chat`, { message: msg }),
    config: () => fetchJSON<{ provider: string }>(`${BASE}/ai/config`),
  },
  permissions: {
    status: () => fetchJSON<{ level: string; emergency_stop: boolean }>(`${BASE}/permissions/status`),
    setLevel: (level: string) => postJSON<{ status: string }>(`${BASE}/permissions/level`, { level }),
    emergency: (action: 'stop' | 'resume') => postJSON<{ status: string }>(`${BASE}/permissions/emergency/${action}`),
  },
  audit: {
    log: (limit = 100) => fetchJSON<{ entries: { action: string }[]; total: number }>(`${BASE}/audit/log?limit=${limit}`),
  },
  plugins: {
    list: () => fetchJSON<{ plugins: { id: string; name: string }[] }>(`${BASE}/plugins/list`),
    load: (id: string) => postJSON<{ status: string }>(`${BASE}/plugins/${id}/load`),
    toggle: (id: string) => postJSON<{ status: string }>(`${BASE}/plugins/${id}/toggle`),
  },
};

describe('API Layer', () => {
  describe('Monitor', () => {
    it('fetches system info', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ hostname: 'test-pc', os: 'Windows' }),
      });
      const data = await api.monitor.system();
      expect(data.hostname).toBe('test-pc');
      expect(data.os).toBe('Windows');
    });

    it('fetches cpu info', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ percent: 45, cores: { physical: 4, logical: 8 } }),
      });
      const data = await api.monitor.cpu();
      expect(data.percent).toBe(45);
      expect(data.cores.physical).toBe(4);
    });

    it('fetches memory info', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ percent: 60, total: 16_000_000_000 }),
      });
      const data = await api.monitor.memory();
      expect(data.percent).toBe(60);
    });

    it('handles fetch error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      await expect(api.monitor.system()).rejects.toThrow('Network error');
    });

    it('handles non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        text: async () => 'Server error',
      });
      await expect(api.monitor.system()).rejects.toThrow('Server error');
    });

    it('fetches processes', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [{ pid: 1234, name: 'test.exe' }, { pid: 5678, name: 'app.exe' }],
      });
      const data = await api.monitor.processes();
      expect(data.length).toBe(2);
      expect(data[0].name).toBe('test.exe');
    });
  });

  describe('Executor', () => {
    it('sends command and returns result', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ stdout: 'hello world', returncode: 0 }),
      });
      const data = await api.executor.command('echo hello');
      expect(data.stdout).toBe('hello world');
      expect(data.returncode).toBe(0);
    });
  });

  describe('AI', () => {
    it('sends chat message and gets response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ response: 'I am AIVO', model: 'test-model' }),
      });
      const data = await api.ai.chat('Who are you?');
      expect(data.response).toBe('I am AIVO');
    });
  });

  describe('Permissions', () => {
    it('gets permission status', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ level: 'confirm', emergency_stop: false }),
      });
      const data = await api.permissions.status();
      expect(data.level).toBe('confirm');
      expect(data.emergency_stop).toBe(false);
    });

    it('sets permission level', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'saved' }),
      });
      const data = await api.permissions.setLevel('admin');
      expect(data.status).toBe('saved');
    });

    it('triggers emergency stop', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'emergency_stop' }),
      });
      const data = await api.permissions.emergency('stop');
      expect(data.status).toBe('emergency_stop');
    });
  });

  describe('Audit', () => {
    it('fetches audit log', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ entries: [{ action: 'test' }], total: 1 }),
      });
      const data = await api.audit.log();
      expect(data.total).toBe(1);
      expect(data.entries[0].action).toBe('test');
    });
  });

  describe('Plugins', () => {
    it('lists plugins', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ plugins: [{ id: 'hello_world', name: 'Hello World' }] }),
      });
      const data = await api.plugins.list();
      expect(data.plugins.length).toBe(1);
    });
  });
});
