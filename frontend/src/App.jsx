import { Link, Route, Routes, useNavigate } from "react-router-dom";
import "./App.css";
import { AuthProvider, useAuth } from "./context/AuthContext";
import CreateRecord from "./components/CreateRecord";
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
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route
        path="/create"
        element={
          <RequireAuth>
            <CreateRecord />
          </RequireAuth>
        }
      />
      <Route
        path="/update"
        element={
          <RequireAuth>
            <UpdateRecord />
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
