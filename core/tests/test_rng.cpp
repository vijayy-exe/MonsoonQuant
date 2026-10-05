// Minimal, dependency-free test harness (plain asserts, no Catch2):
// Catch2 isn't already present on this machine (unlike cmake/clang/
// libomp) and these are a handful of sanity checks, not a full suite —
// not worth a new external fetch for. See docs/methods/simulator.md
// for the fuller rationale.
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <numeric>
#include <vector>

#include "mq/rng.hpp"

#define CHECK(cond)                                                            \
  do {                                                                         \
    if (!(cond)) {                                                             \
      std::fprintf(stderr, "FAILED: %s (%s:%d)\n", #cond, __FILE__, __LINE__); \
      std::exit(1);                                                            \
    }                                                                          \
  } while (0)

static void test_philox_known_answer_vectors() {
  // Random123's own published kat_vectors (tests/kat_vectors),
  // philox4x32, R=10 — verified bit-for-bit against the upstream
  // library before this header was trusted for anything else.
  {
    auto out = mq::rng::philox4x32_10({0, 0}, {0, 0, 0, 0});
    CHECK(out[0] == 0x6627e8d5u);
    CHECK(out[1] == 0xe169c58du);
    CHECK(out[2] == 0xbc57ac4cu);
    CHECK(out[3] == 0x9b00dbd8u);
  }
  {
    auto out = mq::rng::philox4x32_10(
        {0xffffffffu, 0xffffffffu},
        {0xffffffffu, 0xffffffffu, 0xffffffffu, 0xffffffffu});
    CHECK(out[0] == 0x408f276du);
    CHECK(out[1] == 0x41c83b0eu);
    CHECK(out[2] == 0xa20bc7c6u);
    CHECK(out[3] == 0x6d5451fdu);
  }
  {
    auto out = mq::rng::philox4x32_10(
        {0xa4093822u, 0x299f31d0u},
        {0x243f6a88u, 0x85a308d3u, 0x13198a2eu, 0x03707344u});
    CHECK(out[0] == 0xd16cfe09u);
    CHECK(out[1] == 0x94fdccebu);
    CHECK(out[2] == 0x5001e420u);
    CHECK(out[3] == 0x24126ea1u);
  }
  std::printf("ok: test_philox_known_answer_vectors\n");
}

static void test_determinism_same_inputs_give_same_output() {
  std::array<uint32_t, 2> key = {12345, 67890};
  double a = mq::rng::sample_gamma(key, 3, 10, 2.0, 5.0);
  double b = mq::rng::sample_gamma(key, 3, 10, 2.0, 5.0);
  CHECK(a == b);
  bool w1 = mq::rng::sample_wet(key, 3, 10, 0.5);
  bool w2 = mq::rng::sample_wet(key, 3, 10, 0.5);
  CHECK(w1 == w2);
  std::printf("ok: test_determinism_same_inputs_give_same_output\n");
}

static void test_bernoulli_sample_rate_matches_p_wet() {
  std::array<uint32_t, 2> key = {1, 2};
  const double p = 0.3;
  int wet_count = 0;
  const int n = 200000;
  for (int i = 0; i < n; ++i) {
    if (mq::rng::sample_wet(key, static_cast<uint32_t>(i), 0, p))
      wet_count++;
  }
  double rate = static_cast<double>(wet_count) / n;
  CHECK(std::fabs(rate - p) < 0.01);
  std::printf("ok: test_bernoulli_sample_rate_matches_p_wet (rate=%.4f)\n",
              rate);
}

static void test_gamma_sample_mean_and_variance_match_theory() {
  std::array<uint32_t, 2> key = {7, 8};
  const double shape = 2.5;
  const double scale = 4.0;
  const int n = 200000;
  std::vector<double> samples(n);
  for (int i = 0; i < n; ++i) {
    samples[i] =
        mq::rng::sample_gamma(key, static_cast<uint32_t>(i), 0, shape, scale);
  }
  double mean = std::accumulate(samples.begin(), samples.end(), 0.0) / n;
  double var = 0.0;
  for (double s : samples)
    var += (s - mean) * (s - mean);
  var /= (n - 1);

  double expected_mean = shape * scale;
  double expected_var = shape * scale * scale;
  CHECK(std::fabs(mean - expected_mean) / expected_mean < 0.02);
  CHECK(std::fabs(var - expected_var) / expected_var < 0.05);
  std::printf("ok: test_gamma_sample_mean_and_variance_match_theory (mean=%.3f "
              "var=%.3f)\n",
              mean, var);
}

static void test_gamma_sample_shape_below_one_matches_theory() {
  // Real fitted wet-day amount shape (M5.1, nungambakkam) is 0.316 —
  // this exercises the boost-trick branch with a realistic value,
  // not just a hypothetical one.
  std::array<uint32_t, 2> key = {42, 99};
  const double shape = 0.316;
  const double scale = 10.0;
  const int n = 200000;
  std::vector<double> samples(n);
  for (int i = 0; i < n; ++i) {
    samples[i] =
        mq::rng::sample_gamma(key, static_cast<uint32_t>(i), 0, shape, scale);
  }
  double mean = std::accumulate(samples.begin(), samples.end(), 0.0) / n;
  double expected_mean = shape * scale;
  CHECK(std::fabs(mean - expected_mean) / expected_mean < 0.05);
  std::printf("ok: test_gamma_sample_shape_below_one_matches_theory (mean=%.3f "
              "expect=%.3f)\n",
              mean, expected_mean);
}

static void test_season_effect_is_mean_one_lognormal() {
  std::array<uint32_t, 2> key = {5, 6};
  const double sigma = 0.4;
  const int n = 200000;
  double sum = 0.0;
  for (int i = 0; i < n; ++i) {
    sum += mq::rng::sample_season_effect(key, static_cast<uint32_t>(i), sigma);
  }
  double mean = sum / n;
  CHECK(std::fabs(mean - 1.0) < 0.02);
  CHECK(mq::rng::sample_season_effect(key, 0, 0.0) == 1.0); // sigma=0 -> no-op
  std::printf("ok: test_season_effect_is_mean_one_lognormal (mean=%.4f)\n",
              mean);
}

int main() {
  test_philox_known_answer_vectors();
  test_determinism_same_inputs_give_same_output();
  test_bernoulli_sample_rate_matches_p_wet();
  test_gamma_sample_mean_and_variance_match_theory();
  test_gamma_sample_shape_below_one_matches_theory();
  test_season_effect_is_mean_one_lognormal();
  std::printf("all tests passed\n");
  return 0;
}
