export type Forecast = {
  winter: string
  forecast_oni: number
  model_checkpoint?: string
  model_lead?: number
  input_end?: string
  last_observed_oni?: number
  disclaimer?: string
}

export type Impacts = {
  lat: number
  lon: number
  winter: string
  forecast_oni: number
  temp_anom: number
  precip_anom: number
  snow_anom: number
  temp_phrase: string
  precip_phrase: string
  snow_phrase: string
  confidence: number
  confidence_tag: string
  n_winters?: number
  source?: string
}
