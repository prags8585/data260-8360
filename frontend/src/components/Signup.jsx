import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Signup() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const { signup } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    try {
      await signup(firstName, lastName, email, password, confirmPassword);
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not create account.");
    }
  }

  return (
    <div className="card">
      <h2>Create Account</h2>
      {error && <div className="alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <label>
          First Name
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
        </label>
        <label>
          Last Name
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
        </label>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={6}
            required
          />
        </label>
        <label>
          Confirm Password
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={6}
            required
          />
        </label>
        <button type="submit">Create Account</button>
      </form>
      <p className="muted" style={{ marginTop: "1rem" }}>
        Already have an account? <Link to="/login">Log In</Link>
      </p>
    </div>
  );
}
