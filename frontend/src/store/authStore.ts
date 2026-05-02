import { create } from "zustand";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;

  /**
   * True once hydrate() has run at least once.
   * Pages should wait for this before deciding to redirect.
   * Without this flag, a logged-in user gets kicked to /login
   * on every refresh because the store starts empty before
   * localStorage is read.
   */
  _hydrated: boolean;

  setToken: (token: string) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  isAuthenticated: false,
  _hydrated: false,

  setToken: (token) => {
    localStorage.setItem("token", token);
    set({ token, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, isAuthenticated: false });
  },

  hydrate: () => {
    const token = localStorage.getItem("token");
    set({
      token: token ?? null,
      isAuthenticated: !!token,
      _hydrated: true,       // ← mark hydration as done
    });
  },
}));
