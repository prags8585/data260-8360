import { Link, useLocation, useNavigate } from "react-router-dom";

export default function DeleteRecord({ onDelete }) {
  const location = useLocation();
  const navigate = useNavigate();
  const record = location.state?.record;

  if (!record) {
    return (
      <div className="card">
        <p>No course selected to delete.</p>
        <Link to="/">Back to courses</Link>
      </div>
    );
  }

  async function handleDelete() {
    await onDelete(record.id);
    navigate("/");
  }

  return (
    <div className="card">
      <h2>Delete Course</h2>
      <p>
        Are you sure you want to delete <strong>{record.courseTitle}</strong> ({record.courseCode})?
      </p>
      <button className="danger" onClick={handleDelete}>
        Delete
      </button>
      <Link to="/" className="cancel-link">
        Cancel
      </Link>
    </div>
  );
}
