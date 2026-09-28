import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ({ children }) {
  const { user, checking } = useAuth();
  if (checking) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
