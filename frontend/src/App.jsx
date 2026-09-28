import { Link, Route, Routes, useNavigate } from "react-router-dom";
import "./App.css";
import { api } from "./api";
import { AuthProvider, useAuth } from "./context/AuthContext";
import CreateRecord from "./components/CreateRecord";
import DeleteRecord from "./components/DeleteRecord";
import Home from "./components/Home";
import Login from "./components/Login";
import RequireAuth from "./components/RequireAuth";
import Signup from "./components/Signup";
import UpdateRecord from "./components/UpdateRecord";

function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  return (
    <nav className="navbar">
      <span className="brand">Campus Course Catalogue</span>
      <div className="nav-links">
        <Link to="/">Home</Link>
        {user && <Link to="/create">Add Record</Link>}
        {user ? (
          <>
            <span className="user-chip">{user}</span>
            <button onClick={handleLogout}>Log Out</button>
          </>
        ) : (
          <>
            <Link to="/login">Log In</Link>
            <Link to="/signup">Sign Up</Link>
          </>
        )}
      </div>
    </nav>
  );
}

function AppRoutes() {
  // The mutating calls are lifted up here and passed down as props to the
  // Create/Update/Delete route components, per the assignment's
  // "should accept props to add/update/delete the record".
  const createRecord = (course) => api.createCourse(course);
  const updateRecord = (id, course) => api.updateCourse(id, course);
  const deleteRecord = (id) => api.deleteCourse(id);

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        path="/create"
        element={
          <RequireAuth>
            <CreateRecord onCreate={createRecord} />
          </RequireAuth>
        }
      />
      <Route
        path="/update"
        element={
          <RequireAuth>
            <UpdateRecord onUpdate={updateRecord} />
          </RequireAuth>
        }
      />
      <Route
        path="/delete"
        element={
          <RequireAuth>
            <DeleteRecord onDelete={deleteRecord} />
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Nav />
      <main className="container">
        <AppRoutes />
      </main>
    </AuthProvider>
  );
}
