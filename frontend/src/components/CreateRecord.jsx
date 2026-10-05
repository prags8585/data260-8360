import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { clearError, createCourse } from "../store/coursesSlice";
import { fetchInstructors } from "../store/instructorsSlice";

export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const instructors = useSelector((state) => state.instructors.items);
  const [form, setForm] = useState({ courseTitle: "", courseCode: "", seatsAvailable: 30, instructorId: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    dispatch(clearError());
    dispatch(fetchInstructors());
  }, [dispatch]);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    const payload = { ...form, seatsAvailable: Number(form.seatsAvailable), instructorId: Number(form.instructorId) };
    try {
      await dispatch(createCourse(payload)).unwrap();
      navigate("/");
    } catch (message) {
      setError(String(message));
    }
  }

  return (
    <div className="card">
      <h2>Add Course</h2>
      {error && <div className="alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <label>
          Course Title
          <input value={form.courseTitle} onChange={set("courseTitle")} placeholder="e.g. Cloud Computing" required />
        </label>
        <label>
          Course Code
          <input value={form.courseCode} onChange={set("courseCode")} placeholder="e.g. DATA-270" required />
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
        <button type="submit">Add Course</button>
      </form>
    </div>
  );
}
