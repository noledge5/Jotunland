import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// Fehlgeschlagene Befehle zeigt die Oberfläche selbst an (Meldung unten rechts)
window.addEventListener("unhandledrejection", (ev) => {
  if ((ev.reason as { gemeldet?: boolean } | undefined)?.gemeldet) ev.preventDefault();
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
