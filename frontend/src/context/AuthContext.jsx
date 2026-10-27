import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api";
import { tokenStore } from "../auth_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [role, setRole] = useState(null);
  const [checking, setChecking] = useState(true);

  function apply(me) {
    setUser(me ? me.username : null);
    setRole(me ? me.role : null);
  }

  // On page load: if a token is stored, ask GET /auth/me who it belongs to.
  useEffect(() => {
    if (!tokenStore.get()) {
      setChecking(false);
      return;
    }
    api
      .me()
      .then(apply)
      .catch(() => {
        tokenStore.clear();
        apply(null);
      })
      .finally(() => setChecking(false));
  }, []);

  async function login(username, password) {
    await api.login(username, password);
    apply(await api.me());
  }

  async function signup(firstName, lastName, email, password, confirmPassword) {
    await api.signup(firstName, lastName, email, password, confirmPassword);
    apply(await api.me());
  }

  async function logout() {
    await api.logout();
    apply(null);
  }

  const canWrite = role === "writer" || role === "moderator";
  const canDelete = role === "moderator";

  return (
    <AuthContext.Provider value={{ user, role, canWrite, canDelete, checking, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
