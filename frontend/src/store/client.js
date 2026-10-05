import axios from "axios";

// One axios instance for every thunk. withCredentials sends the HTTP-only
// session cookie that /api/auth/login set.
export const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://localhost:8260",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// FastAPI returns {detail: "..."} for 404/409 and {detail: [{msg, loc}]} for 422.
export function errorMessage(err) {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc?.slice(1).join(".") || "request"}: ${d.msg}`).join("; ");
  }
  return detail || err.message || "Request failed";
}
