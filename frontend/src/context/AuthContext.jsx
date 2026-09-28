import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((data) => setUser(data.email))
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  async function login(email, password) {
    const data = await api.login(email, password);
    setUser(data.email);
  }

  async function signup(firstName, lastName, email, password, confirmPassword) {
    const data = await api.signup(firstName, lastName, email, password, confirmPassword);
    setUser(data.email);
  }

  async function logout() {
    await api.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, checking, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
