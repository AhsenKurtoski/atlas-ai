/**
 * ApiService singleton — unico punto di accesso al backend ATLAS AI.
 *
 * Responsabilità:
 *   - Base URL da config.getApiUrl()
 *   - Timeout per tipo di richiesta (default 15s, audio 60s, chat agente 120s)
 *   - Token Bearer automatico da AsyncStorage
 *   - Errori uniformi (`ApiError` con status HTTP) e gestione 401
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import CONFIG from '../config';

export interface PinAuthResult {
  auth: boolean;
  profilo?: string;
  slug?: string;
  token?: string;
  expires_in?: number;
  message?: string;
}

export interface MeResult {
  slug: string;
  nome: string;
  lingua_madre: string;
  livello_italiano: string;
  expires_at?: number | null;
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

export interface DashboardData {
  todos_totali: number;
  todos_pendenti: number;
  spesa_mese: number;
  dispositivi_notifiche: number;
  punti_italiano: number;
  streak_italiano: number;
}

export interface TodoRow {
  id?: string | null;
  task?: string;
  assegnato_a?: string;
  done?: boolean;
  created?: string | null;
}

export interface BudgetData {
  totale: number;
  dettaglio: Array<{ categoria: string; importo: number; percentuale?: number }>;
}

export interface ProfileRow {
  nome: string;
  livello_italiano: string;
  lingua_madre?: string;
}

export interface AppSettings {
  automazioni: Record<string, boolean>;
  notifiche: Record<string, boolean>;
  soglie: Record<string, number>;
}

export interface LessonData {
  lezione: {
    id: string;
    titolo: string;
    spiegazione: string;
    esempi: string[];
    esercizio: string;
    livello: string;
    data: string;
  };
  progresso: ItalianProgress;
}

export interface QuizQuestion {
  id: string;
  livello: string;
  domanda: string;
  opzioni: string[];
}

export interface QuizResult {
  corrette: number;
  totale: number;
  punteggio: number;
  percentuale: number;
  dettaglio: Array<{ id: string; corretta: boolean; risposta_giusta: string; spiegazione: string }>;
  progresso: ItalianProgress;
}

export interface ItalianProgress {
  punti: number;
  streak: number;
  esercizi: number;
}

export interface LeaderboardRow {
  slug: string;
  nome: string;
  punti: number;
  streak: number;
}

export interface GoogleStatus {
  configurato: boolean;
  connesso: boolean;
  email: string;
  redirect_uri: string;
  istruzioni: string;
}

/** Errore HTTP tipizzato: `status` permette di distinguere 401/422/503. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

type RequestOptions = { token?: string; timeoutMs?: number };

class ApiService {
  private static _instance: ApiService | null = null;
  private baseUrl: string;
  private timeout: number;
  private unauthorizedHandler: (() => void) | null = null;

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

  /** Registra una callback da eseguire quando la sessione scade (HTTP 401). */
  setUnauthorizedHandler(handler: (() => void) | null): void {
    this.unauthorizedHandler = handler;
  }

  private async _request<T>(
    method: 'GET' | 'POST' | 'DELETE',
    path: string,
    body?: unknown,
    opts?: RequestOptions
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    const token = opts?.token ?? (await AsyncStorage.getItem(CONFIG.STORAGE_AUTH_TOKEN_KEY));
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutMs = opts?.timeoutMs ?? this.timeout;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });

      const text = await response.text();
      let data: any = {};
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = { message: text };
        }
      }

      if (!response.ok) {
        if (response.status === 401 && path !== '/auth/me' && path !== '/auth/pin') {
          this.unauthorizedHandler?.();
        }
        const rawMessage = data?.message ?? data?.detail;
        const message =
          typeof rawMessage === 'string'
            ? rawMessage
            : `Richiesta fallita (HTTP ${response.status})`;
        throw new ApiError(message, response.status);
      }
      return data as T;
    } catch (error: any) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (error?.name === 'AbortError') {
        throw new ApiError('Il server non risponde (timeout). Riprova.', 408);
      }
      throw new ApiError(
        'Impossibile raggiungere il backend. Controlla che il server sia acceso e la rete.',
        0
      );
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // ---------------- Auth / profili ----------------
  async verifyPin(profileId: string, pin: string): Promise<PinAuthResult> {
    return this._request<PinAuthResult>('POST', '/auth/pin', { profilo: profileId, pin });
  }

  async me(token?: string): Promise<MeResult> {
    return this._request<MeResult>('GET', '/auth/me', undefined, { token });
  }

  async logout(): Promise<GenericResult> {
    return this._request<GenericResult>('POST', '/auth/logout', {});
  }

  async getProfiles(): Promise<Record<string, ProfileRow>> {
    return this._request<Record<string, ProfileRow>>('GET', '/profili');
  }

  async createProfile(params: {
    nome: string;
    pin: string;
    livello_italiano?: string;
    lingua_madre?: string;
  }): Promise<GenericResult<{ slug: string }>> {
    return this._request('POST', '/profili', params);
  }

  async deleteProfile(slug: string): Promise<GenericResult> {
    return this._request('DELETE', `/profili/${encodeURIComponent(slug)}`);
  }

  // ---------------- Chat ----------------
  async sendMessage(
    msg: string,
    profileId: string,
    token?: string,
    image?: { base64: string; mimeType: string }
  ): Promise<ChatResult> {
    return this._request<ChatResult>(
      'POST',
      '/chat',
      {
        msg,
        profilo: profileId,
        ...(image
          ? { immagine_base64: image.base64, immagine_mime_type: image.mimeType }
          : {}),
      },
      { token, timeoutMs: 120000 }
    );
  }

  async transcribeAudio(audioBase64: string, mimeType = 'audio/mp4'): Promise<{ testo: string }> {
    return this._request<{ testo: string }>(
      'POST',
      '/chat/trascrivi',
      { audio_base64: audioBase64, mime_type: mimeType },
      { timeoutMs: 60000 }
    );
  }

  // ---------------- Dashboard / todo / budget ----------------
  async getHealth(): Promise<GenericResult> {
    return this._request<GenericResult>('GET', '/');
  }

  async getDashboard(): Promise<GenericResult<DashboardData>> {
    return this._request('GET', '/dashboard');
  }

  async getTodos(filtro?: string): Promise<GenericResult<TodoRow[]>> {
    const query = filtro ? `?filtro=${encodeURIComponent(filtro)}` : '';
    return this._request('GET', `/todos${query}`);
  }

  async addTodo(task: string, assegnatoA = 'Tutti'): Promise<GenericResult> {
    return this._request('POST', '/todos', { task, assegnato_a: assegnatoA });
  }

  async completeTodoByIndex(index: number): Promise<GenericResult> {
    return this._request('POST', `/todos/${index}/completa`, {});
  }

  async getBudget(): Promise<GenericResult<BudgetData>> {
    return this._request('GET', '/budget');
  }

  async addSpesa(params: {
    importo: number;
    categoria: string;
    descrizione?: string;
  }): Promise<GenericResult> {
    return this._request('POST', '/budget/spesa', params);
  }

  // ---------------- Notifiche ----------------
  async registerPushToken(params: {
    token: string;
    device?: string;
    platform?: string;
  }): Promise<GenericResult> {
    return this._request('POST', '/notifiche/registra', params);
  }

  async unregisterPushToken(token: string): Promise<GenericResult> {
    return this._request('DELETE', `/notifiche/registra?token=${encodeURIComponent(token)}`);
  }

  async sendTestNotification(): Promise<GenericResult> {
    return this._request('POST', '/notifiche/test', {
      titolo: 'Test ATLAS',
      messaggio: 'Le notifiche di ATLAS funzionano! 🎉',
    });
  }

  // ---------------- Impostazioni ----------------
  async getSettings(): Promise<GenericResult<AppSettings>> {
    return this._request('GET', '/impostazioni');
  }

  async updateSettings(patch: Partial<AppSettings>): Promise<GenericResult<AppSettings>> {
    return this._request('POST', '/impostazioni', patch);
  }

  // ---------------- Italiano ----------------
  async getLesson(livello: string): Promise<GenericResult<LessonData>> {
    return this._request('GET', `/italiano/lezione?livello=${encodeURIComponent(livello)}`);
  }

  async getQuiz(
    livello: string,
    n = 5
  ): Promise<GenericResult<{ domande: QuizQuestion[]; progresso: ItalianProgress }>> {
    return this._request('GET', `/italiano/quiz?livello=${encodeURIComponent(livello)}&n=${n}`);
  }

  async submitQuiz(
    risposte: Array<{ id: string; scelta: number }>,
    livello: string
  ): Promise<GenericResult<QuizResult>> {
    return this._request('POST', '/italiano/quiz/valuta', { risposte, livello });
  }

  async getProgress(): Promise<GenericResult<{ mio: ItalianProgress; classifica: LeaderboardRow[] }>> {
    return this._request('GET', '/italiano/progressi');
  }

  // ---------------- Google (Gmail + Calendar) ----------------
  async getGoogleStatus(): Promise<GenericResult<GoogleStatus>> {
    return this._request('GET', '/integrazioni/google/stato');
  }

  async getGoogleAuthUrl(): Promise<GenericResult<{ url?: string; configurato?: boolean }>> {
    return this._request('GET', '/integrazioni/google/url');
  }

  async disconnectGoogle(): Promise<GenericResult> {
    return this._request('POST', '/integrazioni/google/disconnetti', {});
  }
}

export const apiService = ApiService.instance;
export default apiService;
