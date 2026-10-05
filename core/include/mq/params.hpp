// The C++ simulator's public data shapes (SPEC §7.4's SimParams/
// SimRequest/SimResult). GLM prediction (Fourier harmonics, link
// functions) stays in Python (mq.pricing.simulator_glm) — these arrays
// are the *already-evaluated* per-day p01/p11/mean_amt/lpa_mm, so the
// C++ side only has to do the inner Monte-Carlo day-loop, never any
// model fitting or feature engineering.
#pragma once

#include <cstdint>
#include <vector>

namespace mq {

struct SimParams {
  std::vector<double> p01; // P(wet tomorrow | dry today), one per simulated day
  std::vector<double> p11; // P(wet tomorrow | wet today), one per simulated day
  std::vector<double> mean_amt; // wet-day Gamma mean, one per simulated day
  std::vector<double> lpa_mm;   // daily LPA, one per simulated day
  double shape = 1.0; // Gamma shape (constant across days, per M5.1 scope)
  double overdispersion_sd = 0.0;
};

struct SimRequest {
  int n_paths = 0;
  int n_days = 0;
  uint64_t seed = 0;
  double observed_to_date = 0.0;
  int start_state = 0; // 0=dry, 1=wet — the state of the day *before* day 0
};

struct SimResult {
  std::vector<double>
      terminal_index; // observed_to_date + cumulative simulated deviation
  std::vector<double>
      seasonal_total_mm; // simulated rain total only (diagnostic)
};

} // namespace mq
