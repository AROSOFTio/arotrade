export type DrawingSource = 'deterministic' | 'ai' | 'scanner' | 'manual'

export type MarketBias = 'bullish' | 'bearish' | 'neutral'
export type MarketTrend = 'uptrend' | 'downtrend' | 'range'
export type MarketVolatility = 'low' | 'normal' | 'high'
export type MarketStructureBias = 'bullish' | 'bearish' | 'mixed'
export type SignalAction = 'BUY' | 'SELL' | 'WAIT' | 'AVOID'

export interface ChartCandle {
  time: string | number
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
  brokerTime?: string | null
}

export interface ChartPoint {
  time: string
  price: number
}

export interface FibonacciLevel {
  ratio: number
  price: number
  label: string
}

export interface DrawingStyle {
  line_color?: string | null
  fill_color?: string | null
  text_color?: string | null
  line_width?: number | null
  line_style?: 'solid' | 'dashed' | 'dotted' | null
  opacity?: number | null
  z_index?: number | null
}

export interface DrawingInvalidation {
  status?: string | null
  reason?: string | null
  invalidated_at?: string | null
  invalidated_by_price?: number | null
  invalidated_by_time?: string | null
  related_drawing_id?: string | null
}

export interface BaseDrawing {
  id: string
  type: DrawingType
  symbol: string
  timeframe: string
  source: DrawingSource
  confidence: number
  label: string
  enabled: boolean
  created_at: string
  expires_at?: string | null
  style: DrawingStyle
  time_start?: string | null
  time_end?: string | null
  price_start?: number | null
  price_end?: number | null
  price_low?: number | null
  price_high?: number | null
  entry_low?: number | null
  entry_high?: number | null
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  target_price?: number | null
  anchor_points: ChartPoint[]
  levels: FibonacciLevel[]
  state?: string | null
  metadata: Record<string, unknown>
  invalidation?: DrawingInvalidation | null
}

export interface HorizontalLineDrawing extends BaseDrawing {
  type: 'horizontal_line'
}
export interface TrendLineDrawing extends BaseDrawing {
  type: 'trend_line'
}
export interface RayDrawing extends BaseDrawing {
  type: 'ray'
}
export interface RectangleDrawing extends BaseDrawing {
  type: 'rectangle'
}
export interface SupportZoneDrawing extends BaseDrawing {
  type: 'support_zone'
}
export interface ResistanceZoneDrawing extends BaseDrawing {
  type: 'resistance_zone'
}
export interface SupplyZoneDrawing extends BaseDrawing {
  type: 'supply_zone'
}
export interface DemandZoneDrawing extends BaseDrawing {
  type: 'demand_zone'
}
export interface OrderBlockDrawing extends BaseDrawing {
  type: 'order_block'
}
export interface BreakerBlockDrawing extends BaseDrawing {
  type: 'breaker_block'
}
export interface FairValueGapDrawing extends BaseDrawing {
  type: 'fair_value_gap'
}
export interface LiquidityZoneDrawing extends BaseDrawing {
  type: 'liquidity_zone'
}
export interface SwingHighDrawing extends BaseDrawing {
  type: 'swing_high'
}
export interface SwingLowDrawing extends BaseDrawing {
  type: 'swing_low'
}
export interface FibonacciDrawing extends BaseDrawing {
  type: 'fibonacci'
}
export interface EntryZoneDrawing extends BaseDrawing {
  type: 'entry_zone'
}
export interface StopLossDrawing extends BaseDrawing {
  type: 'stop_loss'
}
export interface TakeProfitDrawing extends BaseDrawing {
  type: 'take_profit'
}
export interface RiskRewardBoxDrawing extends BaseDrawing {
  type: 'risk_reward_box'
}
export interface TextLabelDrawing extends BaseDrawing {
  type: 'text_label'
}
export interface SignalMarkerDrawing extends BaseDrawing {
  type: 'signal_marker'
}

export type DrawingType =
  | 'horizontal_line'
  | 'trend_line'
  | 'ray'
  | 'rectangle'
  | 'support_zone'
  | 'resistance_zone'
  | 'supply_zone'
  | 'demand_zone'
  | 'order_block'
  | 'breaker_block'
  | 'fair_value_gap'
  | 'liquidity_zone'
  | 'swing_high'
  | 'swing_low'
  | 'fibonacci'
  | 'entry_zone'
  | 'stop_loss'
  | 'take_profit'
  | 'risk_reward_box'
  | 'text_label'
  | 'signal_marker'

export type ChartDrawing =
  | HorizontalLineDrawing
  | TrendLineDrawing
  | RayDrawing
  | RectangleDrawing
  | SupportZoneDrawing
  | ResistanceZoneDrawing
  | SupplyZoneDrawing
  | DemandZoneDrawing
  | OrderBlockDrawing
  | BreakerBlockDrawing
  | FairValueGapDrawing
  | LiquidityZoneDrawing
  | SwingHighDrawing
  | SwingLowDrawing
  | FibonacciDrawing
  | EntryZoneDrawing
  | StopLossDrawing
  | TakeProfitDrawing
  | RiskRewardBoxDrawing
  | TextLabelDrawing
  | SignalMarkerDrawing

export interface MarketState {
  bias: MarketBias
  trend: MarketTrend
  volatility: MarketVolatility
  structure: MarketStructureBias
  current_price?: number | null
  atr?: number | null
}

export interface IndicatorSummary {
  ema20?: number | null
  ema50?: number | null
  ema200?: number | null
  rsi14?: number | null
  macd?: number | null
  macd_signal?: number | null
  macd_histogram?: number | null
  atr14?: number | null
}

export interface SignalSummary {
  action: SignalAction
  confidence: number
  entry_min?: number | null
  entry_max?: number | null
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  risk_reward?: number | null
  invalidation?: string | null
  reasons: string[]
  warnings: string[]
}

export interface ExplanationSummary {
  summary: string
  observations: string[]
  plan: string
  risk_note: string
}

export interface ChartAnalysisResponse {
  symbol: string
  broker_symbol: string
  timeframe: string
  generated_at: string
  last_candle_time: string
  analysis_version: string
  market_state: MarketState
  indicators: IndicatorSummary
  drawings: ChartDrawing[]
  signal: SignalSummary
  explanation: ExplanationSummary
  warnings: string[]
}
