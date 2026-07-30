/**
 * ApiService singleton — wrapper centralizzato per il backend ATLAS AI.
 *
 * Tutte le chiamate HTTP al backend passano da qui:
 *   - Base URL da config.getApiUrl()
 *   - Timeout condiviso
 *   - Parsing JSON centralizzato + gestione errori uniforme
 *   - Token auth (se presente) in header Authorization
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import CONFIG from '../config';

export interface PinAuthResult {
  auth: boolean;
  profilo?: string;
  token?: string;
  message?: string;
}

export interface ChatResult {
  reply: string;
  function_called?: string | null;
  latency_ms?: number | null;
}

export interface GenericResult<T = unknown> {
  status: string;
  message?: string;
  data?: T;
}

class ApiService {
  private static _instance: ApiService | null = null;
  private baseUrl: string;
  private timeout: number;

  private constructor() {
    this.baseUrl = CONFIG.API_URL;
    this.timeout = CONFIG.REQUEST_TIMEOUT_MS;
  }

  static get instance(): ApiService {
    if (!ApiService._instance) {
      ApiService._instance = new ApiService();
    }
    return ApiService._instance;
  }

  async getBaseUrl(): Promise<string> {
    return this.baseUrl;
  }

  private async _request<T>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown,
    opts?: { token?: string; skipContentType?: boolean }
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {};
    if (!opts?.skipContentType && body) {
      headers['Content-Type'] = 'application/json';
    }
    const token = opts?.token ?? (await AsyncStorage.getItem(CONFIG.STORAGE_AUTH_TOKEN_KEY));
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const resp = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const text = await resp.text();
      let data: any;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { status: 'error', message: text };
      }
      if (!resp.ok) {
        const msg =
          (data && (data.message || data.detail)) ||
          `Richiesta fallita (HTTP ${resp.status})`;
        throw new Error(msg);
      }
      return data as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async verifyPin(profileId: string, pin: string): Promise<PinAuthResult> {
    return this._request<PinAuthResult>('POST', '/auth/pin', {
      profilo: profileId,
      pin,
    });
  }

  async sendMessage(msg: string, profileId: string, token?: string): Promise<ChatResult> {
    const body: Record<string, unknown> = { msg, profilo: profileId };
    if (token) body.token = token;
    return this._request<ChatResult>('POST', '/chat', body, { token });
  }

  async getHealth(): Promise<GenericResult> {
    return this._request<GenericResult>('GET', '/');
  }

  async getDashboard(): Promise<GenericResult> {
    return this._request<GenericResult>('GET', '/');
  }

  async getBudget(): Promise<GenericResult<{ totale: number; dettaglio: Array<{ categoria: string; importo: number; percentuale?: number }> }>> {
    return this._request('GET', '/budget');
  }

  async addSpesa(params: {
    importo: number;
    categoria: string;
    descrizione?: string;
    slug: string;
  }): Promise<GenericResult> {
    return this._request('POST', '/budget/spesa', params);
  }

  async getTodos(filtro?: string): Promise<GenericResult> {
    const qs = filtro ? `?filtro=${encodeURIComponent(filtro)}` : '';
    return this._request('GET', `/todos${qs}`);
  }

  async addTodo(task: string, slug: string, assegnatoA = 'Tutti'): Promise<GenericResult> {
    return this._request('POST', '/todos', { task, slug, assegnato_a: assegnatoA });
  }

  async completeTodoByIndex(index: number): Promise<GenericResult> {
    return this._request('POST', `/todos/${index}/completa`);
  }
}

export const apiService = ApiService.instance;
export default apiService;
