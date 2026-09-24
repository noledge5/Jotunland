import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { callService as haCallService, subscribeEntities, type Connection, type HassEntities, type HassEntity } from "home-assistant-js-websocket";
import { connect, loadSettings, needsSetup, saveSettings, type ConnSettings } from "./connection";
import { startDemo, type DemoHome } from "./demo";
import type { Area, DeviceInfo, EntityMeta, RegEntity } from "./types";
import { EMPTY_CONFIG, loadConfig, resolveMapping, resolveRooms, type JotunConfig, type Mapping, type MappingSource, type RoomConfig } from "../config";
import { buildInfos, type EntityInfo } from "../discovery";

export type Status = "setup" | "connecting" | "connected" | "reconnecting" | "error";

interface HassCtx {
  status: Status;
  error?: string;
  settings: ConnSettings;
  isDemo: boolean;
  entities: HassEntities;
  areas: Area[];
  devices: Record<string, DeviceInfo>;
  meta: Record<string, EntityMeta>;
  /** Alle Entitäten mit Geräte-/Herstellerinfos, Grundlage der Erkennung */
  infos: EntityInfo[];
  /** false = Registry nicht lesbar (kein Admin) → keine Räume/Geräte */
  registryAvailable: boolean;
  config: JotunConfig;
  mapping: Mapping;
  mappingSource: Record<string, MappingSource>;
  overrides: Mapping;
  rooms: RoomConfig[];
  areaName: (id?: string | null) => string | undefined;
  callService: (domain: string, service: string, data?: Record<string, unknown>) => Promise<void>;
  ws: <T>(msg: Record<string, unknown>) => Promise<T>;
  refreshRegistry: () => Promise<void>;
  setOverride: (slot: string, entityId: string | null) => Promise<void>;
  applySettings: (s: ConnSettings | null) => void;
}

const Ctx = createContext<HassCtx | null>(null);

const USER_DATA_KEY = "jotunland_mapping";
const LOCAL_MAPPING_KEY = "jotunland.mapping";

function localMapping(): Mapping {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_MAPPING_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function HassProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<ConnSettings>(loadSettings);
  const [status, setStatus] = useState<Status>(needsSetup(settings) ? "setup" : "connecting");
  const [error, setError] = useState<string>();
  const [entities, setEntities] = useState<HassEntities>({});
  const [areas, setAreas] = useState<Area[]>([]);
  const [devices, setDevices] = useState<Record<string, DeviceInfo>>({});
  const [regEntities, setRegEntities] = useState<RegEntity[]>([]);
  const [registryAvailable, setRegistryAvailable] = useState(true);
  const [config, setConfig] = useState<JotunConfig>(EMPTY_CONFIG);
  const [overrides, setOverrides] = useState<Mapping>(localMapping);
  const conn = useRef<Connection | null>(null);
  const demo = useRef<DemoHome | null>(null);

  useEffect(() => {
    loadConfig().then(setConfig);
  }, []);

  const ws = useCallback(<T,>(msg: Record<string, unknown>): Promise<T> => {
    if (demo.current) return demo.current.ws<T>(msg);
    if (!conn.current) return Promise.reject(new Error("Nicht verbunden"));
    return conn.current.sendMessagePromise<T>(msg as { type: string });
  }, []);

  const refreshRegistry = useCallback(async () => {
    try {
      const [a, e, d] = await Promise.all([
        ws<Area[]>({ type: "config/area_registry/list" }),
        ws<RegEntity[]>({ type: "config/entity_registry/list" }),
        ws<DeviceInfo[]>({ type: "config/device_registry/list" }),
      ]);
      setAreas([...a].sort((x, y) => x.name.localeCompare(y.name, "de")));
      setRegEntities(e);
      setDevices(Object.fromEntries(d.map((x) => [x.id, x])));
      setRegistryAvailable(true);
    } catch {
      // Registry braucht Admin-Rechte – ohne geht es auch, nur ohne Räume/Geräte.
      setRegistryAvailable(false);
    }
  }, [ws]);

  /** In der App gewählte Zuordnung: pro HA-Benutzer auf dem Server gespeichert, lokal als Fallback. */
  const loadOverrides = useCallback(async () => {
    try {
      const r = await ws<{ value: Mapping | null }>({ type: "frontend/get_user_data", key: USER_DATA_KEY });
      if (r?.value) setOverrides(r.value);
    } catch {
      /* Demo oder alte HA-Version → localStorage */
    }
  }, [ws]);

  useEffect(() => {
    if (needsSetup(settings)) {
      setStatus("setup");
      return;
    }
    let cancelled = false;
    let unsub: (() => void) | undefined;
    setStatus("connecting");
    setError(undefined);

    if (settings.mode === "demo") {
      demo.current = startDemo((s) => !cancelled && setEntities(s));
      setStatus("connected");
      refreshRegistry();
      return () => {
        cancelled = true;
        demo.current?.stop();
        demo.current = null;
      };
    }

    connect(settings)
      .then((c) => {
        if (cancelled) return c.close();
        conn.current = c;
        c.addEventListener("disconnected", () => setStatus("reconnecting"));
        c.addEventListener("ready", () => setStatus("connected"));
        unsub = subscribeEntities(c, (s) => setEntities(s));
        setStatus("connected");
        refreshRegistry();
        loadOverrides();
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = typeof err === "number" ? (err === 2 ? "Anmeldung fehlgeschlagen (Token ungültig?)" : err === 1 ? "Verbindung zu Home Assistant nicht möglich" : `Fehler ${err}`) : String(err);
        setError(msg);
        setStatus("error");
      });

    return () => {
      cancelled = true;
      unsub?.();
      conn.current?.close();
      conn.current = null;
    };
  }, [settings, refreshRegistry, loadOverrides]);

  const callService = useCallback(async (domain: string, service: string, data?: Record<string, unknown>) => {
    if (demo.current) return demo.current.call(domain, service, data);
    if (!conn.current) throw new Error("Nicht verbunden");
    await haCallService(conn.current, domain, service, data);
  }, []);

  const setOverride = useCallback(
    async (slot: string, entityId: string | null) => {
      const next = { ...overrides };
      if (entityId) next[slot] = entityId;
      else delete next[slot];
      setOverrides(next);
      try {
        localStorage.setItem(LOCAL_MAPPING_KEY, JSON.stringify(next));
      } catch {
        /* egal */
      }
      if (!demo.current) {
        try {
          await ws({ type: "frontend/set_user_data", key: USER_DATA_KEY, value: next });
        } catch {
          /* bleibt lokal */
        }
      }
    },
    [overrides, ws],
  );

  const applySettings = useCallback((s: ConnSettings | null) => {
    saveSettings(s);
    setEntities({});
    setSettings(s ?? loadSettings());
  }, []);

  const meta = useMemo(() => {
    const m: Record<string, EntityMeta> = {};
    for (const r of regEntities) {
      const dev = r.device_id ? devices[r.device_id] : undefined;
      m[r.entity_id] = {
        area_id: r.area_id ?? dev?.area_id ?? undefined,
        device_id: r.device_id ?? undefined,
        platform: r.platform,
        hidden: !!r.entity_category || !!r.hidden_by,
      };
    }
    return m;
  }, [regEntities, devices]);

  const infos = useMemo(() => buildInfos(entities, meta, devices), [entities, meta, devices]);
  const areaName = useCallback((id?: string | null) => areas.find((a) => a.area_id === id)?.name, [areas]);
  const { mapping, source } = useMemo(() => resolveMapping(config, overrides, infos), [config, overrides, infos]);
  const rooms = useMemo(() => resolveRooms(config, infos, areaName), [config, infos, areaName]);

  const value: HassCtx = {
    status,
    error,
    settings,
    isDemo: settings.mode === "demo",
    entities,
    areas,
    devices,
    meta,
    infos,
    registryAvailable,
    config,
    mapping,
    mappingSource: source,
    overrides,
    rooms,
    areaName,
    callService,
    ws,
    refreshRegistry,
    setOverride,
    applySettings,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useHass(): HassCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useHass außerhalb des HassProvider");
  return c;
}

/** Entität per Zuordnungsschlüssel ("wallbox.power") oder direkt per entity_id. */
export function useEntity(idOrSlot?: string): HassEntity | undefined {
  const { entities, mapping } = useHass();
  if (!idOrSlot) return undefined;
  const id = idOrSlot in mapping ? mapping[idOrSlot] : idOrSlot;
  return id ? entities[id] : undefined;
}
