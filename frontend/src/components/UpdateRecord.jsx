import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useSearchParams } from "react-router-dom";
import { clearError, fetchCourses, updateCourse } from "../store/coursesSlice";
import { fetchInstructors } from "../store/instructorsSlice";

// "Select by ID": pick a course from the ID dropdown, its current values
// load from Redux state into the form, and Save dispatches updateCourse.
export default function UpdateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const courses = useSelector((state) => state.courses.items);
  const instructors = useSelector((state) => state.instructors.items);
  const [selectedId, setSelectedId] = useState(params.get("id") || "");
  const [form, setForm] = useState({ courseTitle: "", courseCode: "", seatsAvailable: 0, instructorId: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    dispatch(clearError());
    dispatch(fetchCourses());
    dispatch(fetchInstructors());
  }, [dispatch]);

  useEffect(() => {
    const course = courses.find((c) => String(c.id) === String(selectedId));
    if (course) {
      setForm({
        courseTitle: course.courseTitle,
        courseCode: course.courseCode,
        seatsAvailable: course.seatsAvailable,
        instructorId: course.instructorId,
      });
    }
  }, [selectedId, courses]);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const payload = {
      id: Number(selectedId),
      ...form,
      seatsAvailable: Number(form.seatsAvailable),
      instructorId: Number(form.instructorId),
    };
    try {
      await dispatch(updateCourse(payload)).unwrap();
      navigate("/");
    } catch (message) {
      setError(String(message));
    }
  }

  return (
    <div className="card">
      <h2>Update Course</h2>
      {error && <div className="alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <label>
          Course ID
          <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)} required>
            <option value="">Select a course by ID…</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.id} — {c.courseCode}
              </option>
            ))}
          </select>
        </label>
        <label>
          Course Title
          <input value={form.courseTitle} onChange={set("courseTitle")} required />
        </label>
        <label>
          Course Code
          <input value={form.courseCode} onChange={set("courseCode")} required />
        </label>
        <label>
          Seats Available
          <input type="number" min="0" value={form.seatsAvailable} onChange={set("seatsAvailable")} required />
        </label>
        <label>
          Instructor
          <select value={form.instructorId} onChange={set("instructorId")} required>
            <option value="">Select an instructor…</option>
            {instructors.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!selectedId}>
          Save Changes
        </button>
      </form>
    </div>
  );
}
