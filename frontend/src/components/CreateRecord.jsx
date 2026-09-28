import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function CreateRecord({ onCreate }) {
  const [courseTitle, setCourseTitle] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await onCreate({ courseTitle, courseCode });
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not add course.");
    }
  }

  return (
    <div className="card">
      <h2>Add Course</h2>
      {error && <div className="alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <label>
          Course Title
          <input
            value={courseTitle}
            onChange={(e) => setCourseTitle(e.target.value)}
            placeholder="e.g. Introduction to Distributed Systems"
            required
          />
        </label>
        <label>
          Course Code
          <input
            value={courseCode}
            onChange={(e) => setCourseCode(e.target.value)}
            placeholder="e.g. DATA-260"
            required
          />
        </label>
        <button type="submit">Add Course</button>
      </form>
    </div>
  );
}
