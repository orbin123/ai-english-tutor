import { api } from "./api";
import type { LoginInput, RegisterInput } from "./validators/auth";

// Backend response shapes
export interface UserOut {
  id: number;
  email: string;
  name: string;
  diagnosis_completed: boolean;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
}

export const authApi = {
  signup: (data: RegisterInput) =>
    api.post<UserOut>("/auth/signup", data).then((r) => r.data),

  login: (data: LoginInput) =>
    api.post<TokenOut>("/auth/login", data).then((r) => r.data),

  me: () => api.get<UserOut>("/auth/me").then((r) => r.data),
};