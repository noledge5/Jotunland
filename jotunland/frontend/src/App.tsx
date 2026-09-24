import { useEffect, useState } from "react";
import { Flame, LayoutGrid, Lightbulb, Mountain, Settings, Workflow, Zap } from "lucide-react";
import { HassProvider, useHass } from "./ha/HassContext";
import { Overview } from "./views/Overview";
import { Heating } from "./views/Heating";
import { Energy } from "./views/Energy";
import { Devices } from "./views/Devices";
import { Automations } from "./views/Automations";
import { Setup } from "./views/Setup";
import { Connect } from "./views/Connect";

const ROUTES = [
  { path: "", label: "Übersicht", short: "Start", icon: LayoutGrid, view: Overview },
  { path: "heizung", label: "Heizung", icon: Flame, view: Heating },
  { path: "energie", label: "Energie", icon: Zap, view: Energy },
  { path: "geraete", label: "Geräte", icon: Lightbulb, view: Devices },
  { path: "automationen", label: "Automationen", short: "Abläufe", icon: Workflow, view: Automations },
  { path: "einrichtung", label: "Einrichtung", short: "Setup", icon: Settings, view: Setup },
];

function useRoute() {
  const read = () => window.location.hash.replace(/^#\/?/, "");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

function Shell() {
  const { status, isDemo, config } = useHass();
  const route = useRoute();
  if (status === "setup" || status === "error") return <Connect />;
  const current = ROUTES.find((r) => r.path === route) ?? ROUTES[0];
  const View = current.view;

  return (
    <div className="shell">
      <nav className="nav" aria-label="Hauptnavigation">
        <div className="brand"><Mountain size={22} /> <span>{config.title}</span></div>
        {ROUTES.map((r) => (
          <a key={r.path} href={`#/${r.path}`} className={r === current ? "active" : ""} aria-current={r === current ? "page" : undefined}>
            <r.icon size={20} />
            <span className={"short" in r ? "long" : undefined}>{r.label}</span>
            {"short" in r && <span className="short">{r.short}</span>}
          </a>
        ))}
        <div className={`conn conn-${status}`}>
          <span className="dot" />
          {isDemo ? "Demo" : status === "connected" ? "Verbunden" : status === "reconnecting" ? "Verbinde neu …" : "Verbinde …"}
        </div>
      </nav>
      <main className="main">
        {isDemo && <div className="demo-banner">Demo-Modus: simulierte Daten. Unter Einrichtung → Verbindung beenden.</div>}
        {status === "connecting" ? <div className="loading">Verbinde mit Home Assistant …</div> : <View />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <HassProvider>
      <Shell />
    </HassProvider>
  );
}
