"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/lib/auth-api";

export default function DashboardPage() {
  const router = useRouter();
  const { isAuthenticated, logout } = useAuthStore();

  // Protect route: kick out if no token
  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  // Fetch user info using the token (proves token works)
  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isAuthenticated,
  });

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!isAuthenticated) return null;

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-gray-200 p-8">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        {isLoading ? (
          <p className="text-gray-600">Loading...</p>
        ) : (
          <p className="text-gray-700">
            Welcome, <span className="font-medium">{user?.name}</span> 👋
          </p>
        )}
        <p className="text-sm text-gray-500">Email: {user?.email}</p>
        <button
          onClick={handleLogout}
          className="rounded bg-gray-800 px-4 py-2 text-white hover:bg-gray-900"
        >
          Log out
        </button>
      </div>
    </main>
  );
}