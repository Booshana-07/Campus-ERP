import React, { createContext, useContext, useEffect, useState } from "react";
import { clearStoredSession, getMe, getStoredToken, storeSession } from "../api/client";

const AuthContext = createContext(null);

const USER_KEY = "campus_emergency_user";

/**
 * Phase 3A: the context now holds a real session token alongside the user.
 *
 * The user object here is only for rendering (name, role badge, menu items).
 * It grants nothing: every protected API call is authorised by the token, and
 * the backend re-checks the role and account status on each request. Editing
 * sessionStorage to say `role: "ADMIN"` changes the menu and nothing else.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = sessionStorage.getItem(USER_KEY);
      // A stored user without a token is a stale session — ignore it.
      return saved && getStoredToken() ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (user) {
      sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      sessionStorage.removeItem(USER_KEY);
    }
  }, [user]);

  // On first load, confirm the stored token is still good and refresh the user
  // from the server. This catches a token that expired while the tab was
  // closed, and an account that was suspended since the last visit — without
  // waiting for the user to trigger some other API call first.
  useEffect(() => {
    let cancelled = false;
    if (!getStoredToken()) return undefined;

    getMe()
      .then((res) => {
        if (!cancelled) setUser(res.data);
      })
      .catch(() => {
        if (!cancelled) {
          clearStoredSession();
          setUser(null);
        }
      });

    return () => {
      cancelled = true;
    };
    // Intentionally runs once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Called after a successful login with the backend's token response. */
  const loginUser = (userData, token) => {
    if (token) storeSession(token);
    setUser(userData);
  };

  const logoutUser = () => {
    clearStoredSession();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loginUser, logoutUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
