const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

function tokenStore() {
  return {
    get access(): string | null {
      try {
        return localStorage.getItem('zynox.access_token');
      } catch {
        return null;
      }
    },
    get refresh(): string | null {
      try {
        return localStorage.getItem('zynox.refresh_token');
      } catch {
        return null;
      }
    },
    set(access: string, refresh: string) {
      try {
        localStorage.setItem('zynox.access_token', access);
        localStorage.setItem('zynox.refresh_token', refresh);
      } catch {
        /* storage may be unavailable — fail silently */
      }
    },
    clear() {
      try {
        localStorage.removeItem('zynox.access_token');
        localStorage.removeItem('zynox.refresh_token');
      } catch {
        /* no-op */
      }
    },
  };
}

export const tokens = tokenStore();

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const refreshToken = tokens.refresh;
  if (!refreshToken) return false;

  const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;

  const data = await response.json();
  tokens.set(data.access_token, data.refresh_token);
  return true;
}

interface ApiOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | number | boolean | null | undefined>;
  skipAuthRefresh?: boolean;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function buildUrl(path: string, params?: ApiOptions['params']): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString().replace(window.location.origin, '');
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = 'GET', body, params, skipAuthRefresh } = options;

  const request = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const accessToken = tokens.access;
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

    return fetch(buildUrl(path, params), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let response = await request();

  if (response.status === 401 && !skipAuthRefresh) {
    if (refreshing === null) {
      refreshing = refreshSession().finally(() => {
        refreshing = null;
      });
    }
    const refreshed = await refreshing;
    if (refreshed) {
      response = await request();
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      (payload && typeof payload === 'object' && 'detail' in payload && String(payload.detail)) ||
      (payload && typeof payload === 'object' && 'error' in payload && String(payload.error)) ||
      response.statusText ||
      'Request failed';
    throw new ApiError(response.status, message, payload);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, params?: ApiOptions['params']) =>
    apiFetch<T>(path, { method: 'GET', params }),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
};
