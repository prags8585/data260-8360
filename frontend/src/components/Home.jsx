import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { deleteCourse, fetchCourses } from "../store/coursesSlice";

// Reads straight from Redux state: when a thunk creates, updates or deletes
// a course the store changes and this list re-renders on its own.
export default function Home() {
  const { user } = useAuth();
  const dispatch = useDispatch();
  const { items: courses, status, error } = useSelector((state) => state.courses);

  useEffect(() => {
    if (user) dispatch(fetchCourses());
  }, [user, dispatch]);

  if (!user) {
    return <p className="login-required">Login required to view courses.</p>;
  }

  return (
    <div>
      <h2>Courses</h2>
      {error && <div className="alert-error">{error}</div>}
      {status === "loading" && courses.length === 0 ? (
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
                <span className="seats">{c.seatsAvailable} seats</span>
                <div className="muted">
                  #{c.id} · {c.instructorName}
                </div>
              </div>
              <div className="row-actions">
                <Link to={`/update?id=${c.id}`}>Edit</Link>
                <button className="delete-btn" onClick={() => dispatch(deleteCourse(c.id))}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
