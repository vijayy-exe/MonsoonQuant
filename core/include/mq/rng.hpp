// Counter-based RNG for the chain-dependent rainfall simulator (SPEC
// §7.4). Philox4x32-10 implemented directly from its published
// constants and round structure (Salmon, Moraes, Dror, Shaw, 2011,
// "Parallel Random Numbers: As Easy as 1, 2, 3") rather than vendoring
// the full upstream Random123 header library — same algorithm, no new
// external dependency to fetch. Verified against Random123's own
// published known-answer test vectors (R=10, all-zero and all-one
// key/counter) in tests/test_rng.cpp.
//
// Every draw below is a pure function of (key, path_id, day_index,
// stream_id, attempt) with no mutable stream state — the reason
// simulate.cpp's OpenMP loop gives bit-identical results regardless of
// how paths are scheduled across threads (SPEC's "same seed ->
// identical output for 1, 4, 8 threads" requirement): there is nothing
// for thread order to perturb.
#pragma once

#include <array>
#include <cmath>
#include <cstdint>

namespace mq::rng {

inline void mulhilo32(uint32_t a, uint32_t b, uint32_t &hi, uint32_t &lo) {
  uint64_t product = static_cast<uint64_t>(a) * static_cast<uint64_t>(b);
  hi = static_cast<uint32_t>(product >> 32);
  lo = static_cast<uint32_t>(product);
}

inline std::array<uint32_t, 4> philox4x32_10(std::array<uint32_t, 2> key,
                                             std::array<uint32_t, 4> ctr) {
  constexpr uint32_t M0 = 0xD2511F53u;
  constexpr uint32_t M1 = 0xCD9E8D57u;
  constexpr uint32_t W0 = 0x9E3779B9u;
  constexpr uint32_t W1 = 0xBB67AE85u;

  std::array<uint32_t, 4> x = ctr;
  std::array<uint32_t, 2> k = key;
  for (int round = 0; round < 10; ++round) {
    if (round > 0) {
      k[0] += W0;
      k[1] += W1;
    }
    uint32_t hi0, lo0, hi1, lo1;
    mulhilo32(M0, x[0], hi0, lo0);
    mulhilo32(M1, x[2], hi1, lo1);
    x = {hi1 ^ x[1] ^ k[0], lo1, hi0 ^ x[3] ^ k[1], lo0};
  }
  return x;
}

constexpr double TWO_PI = 6.283185307179586;
constexpr uint32_t SEASON_DAY_SENTINEL = 0xFFFFFFFFu;

enum StreamId : uint32_t {
  STREAM_OCCURRENCE = 0,
  STREAM_GAMMA_REJECTION = 1,
  STREAM_GAMMA_BOOST = 2,
  STREAM_SEASON_EFFECT = 3,
};

// (0,1) open interval — avoids log(0)/log(1) in Box-Muller and the
// Marsaglia-Tsang acceptance test below.
inline double uniform01_open(uint32_t word) {
  return (static_cast<double>(word) + 0.5) / 4294967296.0;
}

struct Draw4 {
  double u0, u1, u2, u3;
};

inline Draw4 draw4(std::array<uint32_t, 2> key, uint32_t path_id,
                   uint32_t day_index, uint32_t stream_id, uint32_t attempt) {
  auto words = philox4x32_10(key, {path_id, day_index, stream_id, attempt});
  return {uniform01_open(words[0]), uniform01_open(words[1]),
          uniform01_open(words[2]), uniform01_open(words[3])};
}

inline double box_muller_z0(double u1, double u2) {
  return std::sqrt(-2.0 * std::log(u1)) * std::cos(TWO_PI * u2);
}

inline bool sample_wet(std::array<uint32_t, 2> key, uint32_t path_id,
                       uint32_t day_index, double p_wet) {
  Draw4 draw = draw4(key, path_id, day_index, STREAM_OCCURRENCE, 0);
  return draw.u0 < p_wet;
}

// Gamma(shape, scale) via Marsaglia & Tsang (2000) for shape>=1, with
// the standard boost trick (Gamma(a) = Gamma(a+1) * U^(1/a)) for
// shape<1 — the real fitted wet-day amount shape (0.316, M5.1) is in
// this regime, so the boost path is exercised by real data, not just a
// hypothetical. Each rejection-loop retry draws from a fresh Philox
// counter (attempt = 0, 1, 2, ...) rather than advancing any shared
// stream, so a sample's value depends only on (key, path_id, day_index)
// — never on how many retries some OTHER (path, day) needed, or which
// thread ran first.
inline double sample_gamma(std::array<uint32_t, 2> key, uint32_t path_id,
                           uint32_t day_index, double shape, double scale) {
  const bool boost = shape < 1.0;
  const double shape_eff = boost ? shape + 1.0 : shape;
  const double d = shape_eff - 1.0 / 3.0;
  const double c = 1.0 / std::sqrt(9.0 * d);

  double sample = 0.0;
  for (uint32_t attempt = 0;; ++attempt) {
    Draw4 draw =
        draw4(key, path_id, day_index, STREAM_GAMMA_REJECTION, attempt);
    double x = box_muller_z0(draw.u0, draw.u1);
    double v = 1.0 + c * x;
    if (v <= 0.0)
      continue;
    v = v * v * v;
    double x2 = x * x;
    if (std::log(draw.u2) < 0.5 * x2 + d - d * v + d * std::log(v)) {
      sample = d * v;
      break;
    }
  }
  if (boost) {
    Draw4 boost_draw = draw4(key, path_id, day_index, STREAM_GAMMA_BOOST, 0);
    sample *= std::pow(boost_draw.u0, 1.0 / shape);
  }
  return sample * scale;
}

// One lognormal multiplier per path (mean 1, sd `sigma`) — the
// season-level random effect behind the overdispersion fix (SPEC
// §7.4), drawn once per path rather than once per day: see
// mq.pricing.simulator_ref's module docstring for why a per-path
// (not per-day) shock is what actually inflates seasonal-total
// variance.
inline double sample_season_effect(std::array<uint32_t, 2> key,
                                   uint32_t path_id, double sigma) {
  if (sigma <= 0.0)
    return 1.0;
  Draw4 draw =
      draw4(key, path_id, SEASON_DAY_SENTINEL, STREAM_SEASON_EFFECT, 0);
  double z = box_muller_z0(draw.u0, draw.u1);
  return std::exp(-0.5 * sigma * sigma + sigma * z);
}

inline std::array<uint32_t, 2> split_seed(uint64_t seed) {
  return {static_cast<uint32_t>(seed >> 32),
          static_cast<uint32_t>(seed & 0xFFFFFFFFu)};
}

} // namespace mq::rng
