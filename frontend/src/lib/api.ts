import axios from "axios";

// One axios instance,used everywhere in the app
export const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    headers: {"Content-Type": "application/json"},
})

// Request Interceptor: Attach JWT to every request if we have one
api.interceptors.request.use((config) => {
    if (typeof window !== "undefined") {
        const token = localStorage.getItem("token");
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
    }
    return config;

});

// Response interceptor: if backend says 401, log the user out
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401 && typeof window !== "undefined") {
            // Don't auto-redirect on auth endpoints — let the form handle it
            const url: string = error.config?.url ?? "";
            const isAuthEndpoint = url.includes("/auth/login") || url.includes("/auth/signup");

            if (!isAuthEndpoint) {
                // Token is expired or invalid on a protected route — force logout
                localStorage.removeItem("token");
                const { useAuthStore } = require("@/store/authStore");
                useAuthStore.getState().logout();
                window.location.href = "/login";
            }
        }
        return Promise.reject(error);
    }
)