import axios from "axios";
import { tokenStore } from "../auth_token";

// One axios instance for every thunk. HW7: the request interceptor adds the
// JWT as a bearer token (no cookies are involved any more).
export const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://localhost:8260",
  headers: { "Content-Type": "application/json" },
});

client.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// FastAPI returns {detail: "..."} for 401/403/404/409 and {detail: [{msg, loc}]} for 422.
export function errorMessage(err) {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc?.slice(1).join(".") || "request"}: ${d.msg}`).join("; ");
  }
  return detail || err.message || "Request failed";
}
