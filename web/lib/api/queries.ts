import type { Envelope } from "./client";
import { api } from "./client";
import type { components } from "./types";

type ListedSeries = components["schemas"]["ListedSeriesData"];
type ValuationsCompare = components["schemas"]["ValuationsCompareData"];
type QuotesData = components["schemas"]["QuotesData"];
type IndexPathData = components["schemas"]["IndexPathData"];
type DataFreshness = components["schemas"]["DataFreshnessData"];

export async function listContracts(): Promise<ListedSeries[]> {
  const { data, error } = await api.GET("/v1/contracts");
  if (error) throw error;
  return data.data.series;
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
