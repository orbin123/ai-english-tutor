import { create } from "zustand";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  isSuperUser: boolean;

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

/** Decode is_superuser from a JWT's base64url payload. */
function decodeSuperUser(token: string): boolean {
  try {
    const payloadB64 = token.split(".")[1];
    const decoded = JSON.parse(atob(payloadB64));
    return decoded.is_superuser === true;
  } catch {
    return false;
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  isAuthenticated: false,
  isSuperUser: false,
  _hydrated: false,

  setToken: (token) => {
    localStorage.setItem("token", token);
    set({ token, isAuthenticated: true, isSuperUser: decodeSuperUser(token) });
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, isAuthenticated: false, isSuperUser: false });
  },

  hydrate: () => {
    const token = localStorage.getItem("token");
    set({
      token: token ?? null,
      isAuthenticated: !!token,
      isSuperUser: token ? decodeSuperUser(token) : false,
      _hydrated: true,       // ← mark hydration as done
    });
  },
}));
