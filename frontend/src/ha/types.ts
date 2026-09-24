export interface Area {
  area_id: string;
  name: string;
}

export interface DeviceInfo {
  id: string;
  name?: string | null;
  name_by_user?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  area_id?: string | null;
}

/** Eintrag aus der Entitäten-Registry (nur die Felder, die wir brauchen) */
export interface RegEntity {
  entity_id: string;
  area_id?: string | null;
  device_id?: string | null;
  platform?: string;
  entity_category?: string | null;
  hidden_by?: string | null;
  name?: string | null;
}

export interface EntityMeta {
  area_id?: string;
  device_id?: string;
  platform?: string;
  /** config/diagnostic oder ausgeblendet – in der Geräteansicht versteckt */
  hidden?: boolean;
}
