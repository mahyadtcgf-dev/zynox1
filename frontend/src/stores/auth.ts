import { create } from 'zustand';
import { api, tokens } from '@/services/api';
import type { TokenOut, User } from '@/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  initialized: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  initialize: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: false,
  initialized: false,

  initialize: async () => {
    if (!tokens.access) {
      set({ initialized: true });
      return;
    }
    try {
      const user = await api.get<User>('/api/v1/auth/me');
      set({ user, initialized: true });
    } catch {
      tokens.clear();
      set({ user: null, initialized: true });
    }
  },

  login: async (username, password) => {
    set({ loading: true });
    try {
      const data = await api.post<TokenOut>('/api/v1/auth/login', { username, password });
      tokens.set(data.access_token, data.refresh_token);
      set({ user: data.user });
    } finally {
      set({ loading: false });
    }
  },

  logout: async () => {
    const refreshToken = tokens.refresh;
    if (refreshToken) {
      try {
        await api.post('/api/v1/auth/logout', { refresh_token: refreshToken });
      } catch {
        /* session may already be invalid */
      }
    }
    tokens.clear();
    set({ user: null });
  },

  refreshUser: async () => {
    const user = await api.get<User>('/api/v1/auth/me');
    set({ user });
  },

  hasPermission: (permission) => {
    const user = get().user;
    if (!user) return false;
    return user.permissions.includes(permission);
  },
}));
