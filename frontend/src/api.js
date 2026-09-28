// Thin fetch wrapper around the FastAPI JSON API in api.py.
// `credentials: "include"` is required on every call so the browser sends
// the httponly session cookie set by /api/auth/login.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8260";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
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
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  signup: (firstName, lastName, email, password, confirmPassword) =>
    request("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ firstName, lastName, email, password, confirmPassword }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),

  listCourses: () => request("/api/courses"),
  getCourse: (id) => request(`/api/courses/${id}`),
  createCourse: (course) => request("/api/courses", { method: "POST", body: JSON.stringify(course) }),
  updateCourse: (id, course) => request(`/api/courses/${id}`, { method: "PUT", body: JSON.stringify(course) }),
  deleteCourse: (id) => request(`/api/courses/${id}`, { method: "DELETE" }),
};
