#include "mq/simulate.hpp"

#include <stdexcept>

#include "mq/payoff.hpp"
#include "mq/rng.hpp"

#ifdef _OPENMP
#include <omp.h>
#endif

namespace mq {

SimResult simulate(const SimParams &params, const SimRequest &request) {
  const int n = request.n_paths;
  const int d = request.n_days;
  if (static_cast<int>(params.p01.size()) != d ||
      static_cast<int>(params.p11.size()) != d ||
      static_cast<int>(params.mean_amt.size()) != d ||
      static_cast<int>(params.lpa_mm.size()) != d) {
    throw std::invalid_argument(
        "SimParams arrays must each have length request.n_days");
  }

  const auto key = rng::split_seed(request.seed);
  SimResult result;
  result.terminal_index.resize(n);
  result.seasonal_total_mm.resize(n);

  const double *p01 = params.p01.data();
  const double *p11 = params.p11.data();
  const double *mean_amt = params.mean_amt.data();
  const double *lpa_mm = params.lpa_mm.data();
  const double shape = params.shape;
  const double overdispersion_sd = params.overdispersion_sd;
  const int start_state = request.start_state;

#pragma omp parallel for schedule(static)
  for (int p = 0; p < n; ++p) {
    const auto path_id = static_cast<uint32_t>(p);
    const double season_effect =
        rng::sample_season_effect(key, path_id, overdispersion_sd);

    int state = start_state;
    double cumulative_deviation = 0.0;
    double seasonal_total = 0.0;
    for (int t = 0; t < d; ++t) {
      const auto day_id = static_cast<uint32_t>(t);
      const double p_wet = state == 1 ? p11[t] : p01[t];
      const bool wet = rng::sample_wet(key, path_id, day_id, p_wet);

      double amt = 0.0;
      if (wet) {
        const double scale = (mean_amt[t] * season_effect) / shape;
        amt = rng::sample_gamma(key, path_id, day_id, shape, scale);
      }
      cumulative_deviation += amt - lpa_mm[t];
      seasonal_total += amt;
      state = wet ? 1 : 0;
    }
    result.terminal_index[p] =
        identity_payoff(request.observed_to_date + cumulative_deviation);
    result.seasonal_total_mm[p] = seasonal_total;
  }
  return result;
}

} // namespace mq
