import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, auth, clearTokens, isLoggedIn, v1Api } from '../api';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

function mockV1Response(data: unknown) {
  return {
    ok: true,
    json: async () => ({ success: true, data, error: null, requires_confirmation: false, action_id: null, duration_ms: 10, pipeline: null }),
  };
}

describe('API Layer', () => {
  describe('Local desktop authentication', () => {
    it('opens the protected Tauri session without account credentials', async () => {
      clearTokens();
      expect(isLoggedIn()).toBe(false);
      await auth.connectLocal();
      expect(isLoggedIn()).toBe(true);
      clearTokens();
    });
  });

  describe('Feedback and costs', () => {
    it('adapts backend feedback rows for observability', async () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ stats: [
        { provider_id: 'local', task_type: 'simple', total: 2, successes: 2, failures: 0, avg_duration_ms: 100, success_rate: 1 },
        { provider_id: 'local', task_type: 'reasoning', total: 2, successes: 1, failures: 1, avg_duration_ms: 300, success_rate: 0.5 },
      ] }) });
      const result = await api.observability.feedback();
      expect(result.total_feedbacks).toBe(4);
      expect(result.by_provider?.local.success_rate).toBe(0.75);
      expect(result.by_provider?.local.avg_duration_ms).toBe(200);
    });

    it('aggregates model costs by provider', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => ({ total_cost_usd: 0.3, total_tokens: 300 }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ summary: [
          { provider_id: 'cloud', model: 'a', total_cost_usd: 0.1, total_tokens: 100 },
          { provider_id: 'cloud', model: 'b', total_cost_usd: 0.2, total_tokens: 200 },
        ] }) });
      const result = await api.observability.costs();
      expect(result.total_cost).toBe(0.3);
      expect(result.by_provider?.cloud).toEqual({ cost: 0.30000000000000004, tokens: 300 });
    });
  });

  describe('Monitor', () => {
    it('fetches system info', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ hostname: 'test-pc', os: 'Windows' }));
      const data = await api.monitor.system();
      expect(data.hostname).toBe('test-pc');
      const headers = new Headers(mockFetch.mock.calls[0][1].headers);
      expect(headers.get('Authorization')).toBe('Bearer sentinel-dev-session');
    });

    it('fetches cpu info', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ percent: 45, count: 8 }));
      const data = await api.monitor.cpu();
      expect(data.percent).toBe(45);
    });

    it('fetches memory info', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ percent: 60, total: 16_000_000_000 }));
      const data = await api.monitor.memory();
      expect(data.percent).toBe(60);
    });

    it('handles fetch error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      await expect(api.monitor.system()).rejects.toThrow('Network error');
    });

    it('handles non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({ ok: false, text: async () => 'Server error' });
      await expect(api.monitor.system()).rejects.toThrow('Server error');
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('never retries a mutable request after a server error', async () => {
      mockFetch.mockResolvedValueOnce({ ok: false, status: 500, text: async () => 'Server error' });
      await expect(api.ai.setConfig({ provider: 'test', api_key: '', base_url: '', model: '' }))
        .rejects.toThrow('Server error');
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('throws on failed execution', async () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ success: false, error: 'Denied', data: null }) });
      await expect(api.monitor.cpu()).rejects.toThrow('Denied');
    });

    it('fetches processes', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ processes: [{ pid: 1234, name: 'test.exe' }], total: 1 }));
      const data = await api.monitor.processes();
      expect(data.processes.length).toBe(1);
    });
  });

  describe('AI', () => {
    it('sends chat message and gets response', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ response: 'I am Sentinel' }));
      const data = await api.ai.chat('Who are you?');
      expect(data.response).toBe('I am Sentinel');
    });

    it('gets config', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ provider: 'openrouter' }));
      const data = await api.ai.config();
      expect(data.provider).toBe('openrouter');
    });

    it('sets config', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ status: 'saved' }));
      const data = await api.ai.setConfig({ provider: 'test', api_key: '', base_url: '', model: '' });
      expect(data.status).toBe('saved');
    });
  });

  describe('Permissions', () => {
    it('gets permission status', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ level: 'confirm', emergency_stop: false, pending_actions: 0 }));
      const data = await api.permissions.status();
      expect(data.level).toBe('confirm');
    });

    it('sets permission level', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ status: 'ok', level: 'admin' }));
      const data = await api.permissions.setLevel('admin');
      expect(data.status).toBe('ok');
    });

    it('triggers emergency stop', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ status: 'emergency_stop_activated' }));
      const data = await api.permissions.emergency('stop');
      expect(data.status).toBe('emergency_stop_activated');
    });
  });

  describe('Plugins', () => {
    it('lists plugins', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ plugins: [{ id: 'hello_world', name: 'Hello World' }] }));
      const data = await api.plugins.list();
      expect(data.plugins.length).toBe(1);
    });

    it('loads a plugin', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ status: 'loaded' }));
      const data = await api.plugins.load('test');
      expect(data.status).toBe('loaded');
    });
  });

  describe('Fleet', () => {
    it('gets fleet status', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ local_ip: '192.168.1.1', remote_enabled: false }));
      const data = await api.fleet.status();
      expect(data.local_ip).toBe('192.168.1.1');
    });
  });

  describe('Sentinel', () => {
    it('persists and deletes conversation history through the owner-scoped API', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => ({ session_id: 'thread-1', title: 'Python', messages: [] }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ deleted: true, session_id: 'thread-1' }) });

      await api.sentinel.saveConversation('thread-1', { title: 'Python', messages: [] });
      await api.sentinel.deleteConversation('thread-1');

      expect(mockFetch.mock.calls[0][0]).toContain('/api/sentinel/conversations/thread-1');
      expect(mockFetch.mock.calls[0][1].method).toBe('PUT');
      expect(mockFetch.mock.calls[1][1].method).toBe('DELETE');
    });

    it('parses progressive chat events even when network chunks split JSON lines', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode('{"type":"status","stage":"planning"}\n{"type":"del'));
          controller.enqueue(encoder.encode('ta","text":"Hola "}\n{"type":"delta","text":"mundo"}\n'));
          controller.enqueue(encoder.encode('{"type":"done"}\n'));
          controller.close();
        },
      });
      mockFetch.mockResolvedValueOnce({ ok: true, body: stream });
      const events: { type: string; text?: string }[] = [];

      await api.sentinel.streamChat('hola', [], 'conversation-1', (event) => events.push(event));

      expect(events.map((event) => event.type)).toEqual(['status', 'delta', 'delta', 'done']);
      expect(events.filter((event) => event.type === 'delta').map((event) => event.text).join('')).toBe('Hola mundo');
      const request = mockFetch.mock.calls[0];
      expect(request[0]).toContain('/api/sentinel/chat/stream');
      expect(JSON.parse(request[1].body)).toMatchObject({ session_id: 'conversation-1' });
    });

    it('processes natural language', async () => {
      mockFetch.mockResolvedValueOnce(mockV1Response({ approved: true, intent: { action: 'run', target: 'echo', confidence: 0.9, raw_input: 'echo hello' }, plan: { risk_score: 0, steps: [] }, decision: 'approve', tool_result: null }));
      const data = await api.sentinel.process('echo hello');
      expect(data.approved).toBe(true);
      expect(data.intent.action).toBe('run');
    });
  });

  describe('v1Api', () => {
    it('may retry a read-only request after a transient server error', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: false, status: 503, text: async () => 'Unavailable' })
        .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [] });
      await expect(v1Api.listPolicies()).resolves.toEqual([]);
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it('lists policies', async () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'test', description: 'test policy', source: 'yaml' }] });
      const data = await v1Api.listPolicies();
      expect(data.length).toBe(1);
    });

    it('lists audit', async () => {
      mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ entries: [{ action: 'test' }], total: 1 }) });
      const data = await v1Api.listAudit();
      expect(data.total).toBe(1);
    });
  });
});
