import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../context/AuthContext";

export default function Home() {
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    api
      .listCourses()
      .then(setCourses)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [user]);

  if (!user) {
    return <p className="login-required">Login required to view courses.</p>;
  }

  return (
    <div>
      <h2>Courses</h2>
      {error && <div className="alert-error">{error}</div>}
      {loading ? (
        <p className="muted">
          <span className="spinner" />
          Loading courses…
        </p>
      ) : courses.length === 0 ? (
        <div className="empty-state">No courses yet. Add one to get started.</div>
      ) : (
        <ul className="course-list">
          {courses.map((c) => (
            <li key={c.id}>
              <div>
                <strong>{c.courseTitle}</strong>
                <span className="course-code">{c.courseCode}</span>
              </div>
              <div className="row-actions">
                <Link to="/update" state={{ record: c }}>
                  Edit
                </Link>
                <Link to="/delete" state={{ record: c }}>
                  Delete
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
