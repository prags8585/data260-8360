// HW7: the JWT lives in localStorage and is sent as "Authorization: Bearer <token>"
// on every call (the HW4 session cookie is no longer used).
const KEY = "s8360_access_token";

export const tokenStore = {
  get: () => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set: (token) => {
    try {
      localStorage.setItem(KEY, token);
    } catch {
      // storage unavailable (private mode): the token only lives for this page load
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(KEY);
    } catch {
      // nothing to clear
    }
  },
};
