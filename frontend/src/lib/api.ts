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
            localStorage.removeItem("token");
            // Hard redirect - simplest way to fully reset state
            window.location.href = "/login";
        }
        return Promise.reject(error);
    }
)