import { AppProvider, useAppContext } from "./AppContext";
import HomePage from "./pages/HomePage";
import AboutPage from "./pages/AboutPage";
import ManualPage from "./pages/ManualPage";
import PrivacyPage from "./pages/PrivacyPage";
import SettingsPage from "./pages/SettingsPage";
import "./App.css";

function Router() {
  const { page, error, setError } = useAppContext();

  return (
    <div className="container">
      {error && (
        <div className="error-banner">
          <p>{error}</p>
          <button onClick={() => setError(null)} className="btn-dismiss">
            Dismiss
          </button>
        </div>
      )}
      {page === "capture" && <HomePage />}
      {page === "about" && <AboutPage />}
      {page === "manual" && <ManualPage />}
      {page === "privacy" && <PrivacyPage />}
      {page === "settings" && <SettingsPage />}
    </div>
  );
}

function App() {
  return (
    <AppProvider>
      <Router />
      <footer style={{ textAlign: "center", padding: "16px", fontSize: "12px", color: "#9ca3af" }}>
        © 2026 BKlein Digital Labs. All rights reserved.
      </footer>
    </AppProvider>
  );
}

export default App;
