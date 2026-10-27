// Thin fetch wrapper around the FastAPI JSON API (jwt_auth.py + catalog_api.py).
// HW7: every call carries the JWT as a bearer token instead of a session cookie.
import { tokenStore } from "./auth_token";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8260";

async function request(path, options = {}) {
  const token = tokenStore.get();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response had no JSON body
    }
    const error = new Error(detail);
    error.status = res.status;
    throw error;
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: async (username, password) => {
    const data = await request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
    tokenStore.set(data.access_token);
    return data;
  },
  signup: async (firstName, lastName, email, password, confirmPassword) => {
    const data = await request("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ firstName, lastName, email, password, confirmPassword }),
    });
    tokenStore.set(data.access_token);
    return data;
  },
  logout: async () => tokenStore.clear(),
  me: () => request("/auth/me"),

  listCourses: () => request("/api/courses"),
  getCourse: (id) => request(`/api/courses/${id}`),
  createCourse: (course) => request("/api/courses", { method: "POST", body: JSON.stringify(course) }),
  updateCourse: (id, course) => request(`/api/courses/${id}`, { method: "PUT", body: JSON.stringify(course) }),
  deleteCourse: (id) => request(`/api/courses/${id}`, { method: "DELETE" }),
};
