import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

export default function UpdateRecord({ onUpdate }) {
  const location = useLocation();
  const navigate = useNavigate();
  const record = location.state?.record;

  const [courseTitle, setCourseTitle] = useState(record?.courseTitle || "");
  const [courseCode, setCourseCode] = useState(record?.courseCode || "");
  const [error, setError] = useState("");

  if (!record) {
    return (
      <div className="card">
        <p>No course selected to update.</p>
        <Link to="/">Back to courses</Link>
      </div>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await onUpdate(record.id, { courseTitle, courseCode });
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not update course.");
    }
  }

  return (
    <div className="card">
      <h2>Update Course</h2>
      {error && <div className="alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <label>
          Course Title
          <input value={courseTitle} onChange={(e) => setCourseTitle(e.target.value)} required />
        </label>
        <label>
          Course Code
          <input value={courseCode} onChange={(e) => setCourseCode(e.target.value)} required />
        </label>
        <button type="submit">Save Changes</button>
      </form>
    </div>
  );
}
