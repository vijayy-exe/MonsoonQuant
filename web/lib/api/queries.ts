import type { Envelope } from "./client";
import { api } from "./client";
import type { components } from "./types";

type ListedSeries = components["schemas"]["ListedSeriesData"];
type ValuationsCompare = components["schemas"]["ValuationsCompareData"];
type QuotesData = components["schemas"]["QuotesData"];
type IndexPathData = components["schemas"]["IndexPathData"];
type DataFreshness = components["schemas"]["DataFreshnessData"];
type MPRData = components["schemas"]["MPRData"];
type ForecastData = components["schemas"]["ForecastData"];
type GreeksData = components["schemas"]["GreeksData"];
export type HedgeRequest = components["schemas"]["HedgeRequest"];
type HedgeResponseData = components["schemas"]["HedgeResponseData"];
export type ParametricDesignRequest = components["schemas"]["ParametricDesignRequest"];
type ParametricDesignData = components["schemas"]["ParametricDesignData"];
type TrackRecordData = components["schemas"]["TrackRecordData"];
type VerifyData = components["schemas"]["VerifyData"];
type LedgerRowsData = components["schemas"]["LedgerRowsData"];
type ContractSpecData = components["schemas"]["ContractSpecData"];

export type BasisFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    n_years: number;
    correlation: number;
    rmse: number;
    kendall_tau: number;
    tail_dependence_upper: number;
    tail_dependence_lower: number;
    seasonal_mismatch: number | null;
    hedge_effectiveness: number;
    hedge_ratio: number;
  };
};
export type BasisGeoJson = { type: "FeatureCollection"; features: BasisFeature[] };

export async function listContracts(): Promise<ListedSeries[]> {
  const { data, error } = await api.GET("/v1/contracts");
  if (error) throw error;
  return data.data.series;
}

export async function getContractSpec(
  code: string,
): Promise<Envelope<ContractSpecData> | null> {
  const { data, error } = await api.GET("/v1/contracts/{code}/spec", {
    params: { path: { code } },
  });
  if (error) return null;
  return data;
}

/** Returns null rather than throwing when a series genuinely has no valuations yet. */
export async function getValuationsCompare(
  seriesId: string,
): Promise<Envelope<ValuationsCompare> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/valuations/compare", {
    params: { path: { series_id: seriesId } },
  });
  if (error) return null;
  return data;
}

export async function getQuotes(seriesId: string): Promise<Envelope<QuotesData>> {
  const { data, error } = await api.GET("/v1/series/{series_id}/quotes", {
    params: { path: { series_id: seriesId } },
  });
  if (error) throw error;
  return data;
}

export async function getIndexPath(seriesId: string): Promise<Envelope<IndexPathData> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/index", {
    params: { path: { series_id: seriesId }, query: {} },
  });
  if (error) return null;
  return data;
}

export async function getDataFreshness(): Promise<Envelope<DataFreshness>> {
  const { data, error } = await api.GET("/v1/health/data");
  if (error) throw error;
  return data;
}

export async function getMpr(seriesId: string): Promise<Envelope<MPRData> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/mpr", {
    params: { path: { series_id: seriesId }, query: {} },
  });
  if (error) return null;
  return data;
}

export async function getForecast(seriesId: string): Promise<Envelope<ForecastData> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/forecast", {
    params: { path: { series_id: seriesId }, query: {} },
  });
  if (error) return null;
  return data;
}

/**
 * SPEC §10 page 3's "analog-years table". Real, not stored anywhere --
 * a live on-demand re-run of just `analog_v1`'s own selection step
 * (first hit ~14s uncached, cached after by (contract, as_of, k)).
 * Returns null on error -- most commonly a real data gap (e.g. ONI/DMI
 * not yet published for the current month), an honest-empty case, not
 * a page-breaking one.
 */
export async function getAnalogYears(
  seriesId: string,
): Promise<Envelope<components["schemas"]["AnalogYearsData"]> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/forecast/analog-years", {
    params: { path: { series_id: seriesId }, query: {} },
  });
  if (error) return null;
  return data;
}

export async function getGreeks(seriesId: string): Promise<Envelope<GreeksData> | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/greeks", {
    params: { path: { series_id: seriesId }, query: {} },
  });
  if (error) return null;
  return data;
}

export async function getBasis(
  seriesId: string,
  boxDeg?: number,
): Promise<{ data: BasisGeoJson; meta: Envelope<unknown>["meta"] } | null> {
  const { data, error } = await api.GET("/v1/series/{series_id}/basis", {
    params: { path: { series_id: seriesId }, query: boxDeg ? { box_deg: boxDeg } : {} },
  });
  if (error) return null;
  return data as unknown as { data: BasisGeoJson; meta: Envelope<unknown>["meta"] };
}

export async function postHedge(
  req: HedgeRequest,
): Promise<{ data: HedgeResponseData; meta: Envelope<unknown>["meta"] } | { problem: string }> {
  const { data, error } = await api.POST("/v1/hedge", { body: req });
  if (error) return { problem: errorDetail(error) };
  return data;
}

export async function postParametricDesign(
  req: ParametricDesignRequest,
): Promise<
  { data: ParametricDesignData; meta: Envelope<unknown>["meta"] } | { problem: string }
> {
  const { data, error } = await api.POST("/v1/parametric/design", { body: req });
  if (error) return { problem: errorDetail(error) };
  return data;
}

export async function getTrackRecord(
  contractCode = "RAINCHNNAI",
): Promise<Envelope<TrackRecordData> | null> {
  const { data, error } = await api.GET("/v1/track-record", {
    params: { query: { contract_code: contractCode } },
  });
  if (error) return null;
  return data;
}

/**
 * Returns null on any transient error (e.g. a 429) rather than
 * throwing -- a real bug this once was: an uncaught error here crashed
 * Track Record's *entire* page (Next's generic error boundary), not
 * just this one section, caught via a real rate-limit trip while
 * testing against a cold server.
 */
export async function getLedgerVerify(): Promise<Envelope<VerifyData> | null> {
  const { data, error } = await api.GET("/v1/ledger/verify");
  if (error) return null;
  return data;
}

export async function listLedgerRows(): Promise<Envelope<LedgerRowsData> | null> {
  const { data, error } = await api.GET("/v1/ledger", { params: { query: {} } });
  if (error) return null;
  return data;
}

function errorDetail(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    if ("detail" in error && typeof (error as { detail?: unknown }).detail === "string") {
      return (error as { detail: string }).detail;
    }
    if ("title" in error && typeof (error as { title?: unknown }).title === "string") {
      return (error as { title: string }).title;
    }
  }
  return "Request failed.";
}
